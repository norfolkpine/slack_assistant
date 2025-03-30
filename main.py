# main.py

import os
import time
import hmac
import hashlib
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Header
from fastapi.responses import JSONResponse
from slack_sdk.web import WebClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.tools.slack import SlackTools
from agno.tools.jira import JiraTools
from agno.utils.pprint import pprint_run_response

# === Load env ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

# === Slack Client ===
web_client = WebClient(token=SLACK_BOT_TOKEN)

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
    request: Request,
    command: str = Form(...),
    text: str = Form(...),
    user_id: str = Form(...),
    channel_id: str = Form(...),
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...)
):
    body = await request.body()
    print("\n📨 Received slash command POST request")
    print("Command:", command)
    print("Text:", text)
    print("User:", user_id)
    print("Channel:", channel_id)

    try:
        verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)
    except Exception as e:
        print("❌ Signature verification failed:", e)
        return JSONResponse(content={"response_type": "ephemeral", "text": "⚠️ Unauthorized"})

    if command == "/indo":
        prompt = f"Translate this message to Indonesian: {text.strip()}"
    elif command == "/en":
        prompt = f"Translate this message to English: {text.strip()}"
    else:
        prompt = text

    try:
        print("💭 Prompt:", prompt)
        response: RunResponse = agent.run(prompt)
        return JSONResponse(content={
            "response_type": "in_channel",
            "text": response.content.strip()
        })
    except Exception as e:
        print("❌ Slash command error:", e)
        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": "⚠️ Error processing your command."
        })
