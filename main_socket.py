import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from slack_sdk.web import WebClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.tools.slack import SlackTools
from agno.tools.jira import JiraTools
from agno.utils.pprint import pprint_run_response

# === Load env ===
if os.getenv("GOOGLE_CLOUD_PROJECT"):
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/secrets/SLACK_AGENT_ENV/versions/latest"
    response = client.access_secret_version(request={"name": secret_name})
    env_data = response.payload.data.decode("UTF-8")
    for line in env_data.splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip()
else:
    load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# === Slack Client ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
# Fetch bot user ID dynamically from Slack
response = web_client.auth_test()
BOT_USER_ID = response["user_id"]

# === FastAPI app ===
app = FastAPI()

# === Agno Agent ===
agent = Agent(
    name="Reggie",
    model=OpenAIChat(id="gpt-4o"),
    tools=[SlackTools(), JiraTools()],
    show_tool_calls=True,
    instructions="If translating, return only the translated text."
)

# === In-Memory Processing Tracker ===
# This will store the status of ongoing requests to prevent duplicate processing
processing_tracker = {}

# === Message Handler Logic ===
def handle_message_event(event):
    user = event.get("user")
    text = event.get("text", "")
    channel = event.get("channel")

    if not text or not user or "bot_id" in event:
        return None

    # Strip bot mention if present
    if BOT_USER_ID:
        text = text.replace(f"<@{BOT_USER_ID}>", "").strip()

    if "/indo" in text.lower():
        prompt = f"Translate this message to Indonesian: {text.replace('/indo', '').strip()}"
    elif "/en" in text.lower():
        prompt = f"Translate this message to English: {text.replace('/en', '').strip()}"
    else:
        prompt = text.strip()

    return channel, prompt, user, text.strip()

# === Slack Signature Verification ===
def verify_slack_signature(body: bytes, timestamp: str, signature: str):
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise ValueError("Request too old")

    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode("utf-8")
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(my_signature, signature):
        raise ValueError("Invalid Slack signature")

# === Slash Command Endpoint ===
@app.post("/slack/commands")
async def slash_commands(
    background_tasks: BackgroundTasks,
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...)
):
    body = await request.body()

    try:
        verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)
    except Exception as e:
        print("❌ Signature verification failed:", e)
        return JSONResponse(content={"response_type": "ephemeral", "text": "⚠️ Unauthorized"})

    from urllib.parse import parse_qs
    form = parse_qs(body.decode())
    command = form.get("command", [""])[0]
    text = form.get("text", [""])[0]
    user_id = form.get("user_id", [""])[0]
    channel_id = form.get("channel_id", [""])[0]
    response_url = form.get("response_url", [""])[0]
    thread_ts = form.get("thread_ts", [""])[0] or form.get("message_ts", [""])[0]

    print("\n📨 Received slash command POST request")
    print("Command:", command)
    print("Text:", text)
    print("User:", user_id)
    print("Channel:", channel_id)

    # Define the prompt based on the command
    if command == "/indo":
        prompt = f"Translate this message to Indonesian: {text.strip()}"
    elif command == "/en":
        prompt = f"Translate this message to English: {text.strip()}"
    else:
        prompt = text

    # Check if this request is already being processed
    if processing_tracker.get(user_id):
        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": "⚠️ Your request is already being processed."
        })

    # Mark the user as processing
    processing_tracker[user_id] = True

    try:
        async def run_agent_async():
            try:
                print("💭 Prompt:", prompt)
                response: RunResponse = agent.run(prompt)
                final_text = f">From: <@{user_id}>\n>{text.strip()}\n```\n{response.content.strip()}\n```"
                print("📤 Response:", final_text)
                print(f"🚀 Sending to response_url: {response_url}")
                payload = {
                    "response_type": "in_channel",
                    "text": final_text
                }
                if thread_ts:
                    payload["thread_ts"] = thread_ts
                requests.post(response_url, json=payload)

                # After the task is completed, mark the user as done
                processing_tracker[user_id] = False
            except Exception as e:
                print("❌ Error posting to response_url:", e)
                requests.post(response_url, json={
                    "response_type": "ephemeral",
                    "text": "⚠️ Error processing your command."
                })

        background_tasks.add_task(run_agent_async)

        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": "⏳ Processing your request..."
        })

    except Exception as e:
        print("❌ Slash command setup error:", e)
        processing_tracker[user_id] = False
        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": "⚠️ Something went wrong."
        })


# === Event Callback Webhook ===
@app.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...)
):
    body = await request.body()
    try:
        verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)
    except Exception as e:
        print("❌ Signature verification failed:", e)
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    result = handle_message_event(event)
    if result:
        channel, prompt, user_id, original_text = result

        # Avoid processing multiple times for the same user
        if processing_tracker.get(user_id):
            return {"ok": True}

        # Mark the user as processing
        processing_tracker[user_id] = True

        try:
            print("💭 Prompt:", prompt)
            response: RunResponse = agent.run(prompt)
            final_text = f">From: <@{user_id}>\n>{original_text}\n```\n{response.content.strip()}\n```"
            print("📤 Response:", final_text)
            print(f"🚀 Sending message to Slack channel {channel}...")

            # Strip bot user mention from the final message text
            final_text = final_text.replace(f"<@{BOT_USER_ID}>", "").strip()

            web_client.chat_postMessage(channel=channel, text=final_text)

            # After the task is completed, mark the user as done
            processing_tracker[user_id] = False
        except Exception as e:
            print("❌ Webhook event error:", e)
            processing_tracker[user_id] = False
    return {"ok": True}
