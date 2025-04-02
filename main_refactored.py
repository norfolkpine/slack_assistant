import re
import os
import requests
from threading import Event
from dotenv import load_dotenv
from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.models.google import Gemini
#from agno.tools.slack import SlackTools
from agno.tools.jira import JiraTools
from tools.coingecko import CoinGeckoTools
from tools.custom_slack import SlackTools
from tools.blockscout import BlockscoutTools


def extract_channel_and_ts(url: str) -> tuple:
    pattern = r'https://([a-zA-Z0-9\-]+)\.slack\.com/archives/([A-Za-z0-9]+)/p([0-9]+)'
    
    match = re.match(pattern, url)
    
    if match:
        channel = match.group(2) 
        ts = match.group(3)  
        
        ts_standard = f"{ts[:10]}.{ts[10:]}"
        
        return channel, ts_standard
    else:
        raise ValueError("Invalid Slack message URL format")

# === Load environment variables ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

# === Setup Slack clients ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

# Fetch bot metadata
auth_info = web_client.auth_test()
BOT_USER_ID = auth_info["user_id"]
TEAM_ID = auth_info["team_id"]

# === Setup AI Agent ===
agent = Agent(
    name="Reggie",
    model=OpenAIChat(id="gpt-4o"),
    #model=Gemini(id="gemini-1.5-flash"),
    tools=[SlackTools(), JiraTools(), CoinGeckoTools()],
    show_tool_calls=True,
    instructions= [
        "If translating, return only the translated text. Use Slack tools.",
        "Format using currency symbols",
        "Use tools for getting data such as the price of bitcoin"
    ],
    read_chat_history=True,
    add_history_to_messages=True,
    num_history_responses=10,
)

# === Check for subscription (stubbed) ===
def has_valid_subscription(team_id: str) -> bool:
    VALID_TEAM_IDS = {"T06LP8F3K8V", "T87654321"}
    return team_id in VALID_TEAM_IDS

# Future code for tracking against SaaS service
# def has_valid_subscription(slack_team_id: str) -> bool:
#     try:
#         workspace = SlackWorkspace.objects.get(slack_team_id=slack_team_id)
#         team = workspace.team
#         return team.subscriptions.filter(status="active").exists()
#     except SlackWorkspace.DoesNotExist:
#         return False

# === SocketMode main handler ===
def process(client: SocketModeClient, req: SocketModeRequest):
    print(f"📥 Incoming request: {req.type}")

    # Always acknowledge the event
    try:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    except Exception as e:
        print(f"❗ Failed to ACK Slack request: {e}")
        return

    if not has_valid_subscription(TEAM_ID):
        print("🚫 Unauthorized workspace.")
        channel = req.payload.get("event", {}).get("channel")
        if channel:
            client.web_client.chat_postMessage(
                channel=channel,
                text="⚠️ This workspace does not have an active subscription."
            )
        return

    if req.payload.get("response_url"):
        requests.post(req.payload["response_url"], json={"text": "⚙️ Processing... Please wait."})

    try:
        if req.type == "slash_commands":
            handle_slash_command(req)
        elif req.type == "events_api":
            handle_events_api(req)
        else:
            print(f"ℹ️ Unsupported request type: {req.type}")
    except Exception as e:
        print(f"❌ Error while processing request: {e}")

# === Handle slash commands ===
def handle_slash_command(req: SocketModeRequest):

    command = req.payload.get("command")
    text = req.payload.get("text", "").strip()
    user_id = req.payload.get("user_id")
    response_url = req.payload.get("response_url")

    print(f"📎 Slash command: {command}, Text: {text}")

    if command == '/indo' or command == '/en':
        print(f"🌐 Translation command received: {command}")

        translation_prompts = {
            "/indo": f"Translate this message to informal Indonesian: {text}",
            "/en": f"Translate this message to English: {text}"
        }

        prompt = translation_prompts.get(command)
        if not prompt:
            print("⚠️ Unrecognized slash command.")
            return

        try:
            response: RunResponse = agent.run(prompt)
            translation = response.content.strip()
            final_text = f">From: <@{user_id}>\n>{text}\n```{translation}```"

            requests.post(
                response_url,
                json={
                    "response_type": "in_channel",  # or "ephemeral" for private response
                    "text": final_text
                }
            )

        except Exception as e:
            print(f"❌ Error in slash command handler: {e}")
            requests.post(
                response_url,
                json={"text": "⚠️ Sorry, something went wrong while processing your translation request."}
            )

    elif command == '/summarize':
        channel, message_ts = extract_channel_and_ts(text)
        print(f"📜 Summarizing message from channel: {channel}, ts: {message_ts}")
        history_messages = []
        try:
            response = client.web_client.conversations_replies(
                channel=channel,
                ts=message_ts, 
            )

            if response.get("messages"):
                history_messages = [
                    f"<@{msg['user']}>: {msg['text']}"
                    for msg in reversed(response["messages"]) 
                    if "user" in msg and "text" in msg
                ]
                context = "\n".join(history_messages)
                full_prompt = f"Summarize comprehensively, skimmable, but keeping important details.\nThread history:\n{context}"
                response: RunResponse = agent.run(full_prompt)
                final_text = f">From: <@{user_id}>\n>{text}\n```{response.content.strip()}```"
                
                client.web_client.chat_postMessage(
                    channel=channel,
                    text=final_text,
                )
                    
        except Exception as e:
            print(f"⚠️ Failed to fetch thread history: {e}")
            return


   

# === Handle Events API (mentions and DMs) ===
def handle_events_api(req: SocketModeRequest):
    event = req.payload.get("event", {})
    user = event.get("user")
    bot_id = event.get("bot_id")
    if bot_id or user == BOT_USER_ID:
        print("🤖 Ignoring bot message.")
        return

    event_type = event.get("type")
    channel = event.get("channel")
    channel_type = event.get("channel_type")
    text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")  # thread_ts or message timestamp
    message_ts = event.get("ts")

    # React to acknowledge
    try:
        client.web_client.reactions_add(
            name="eyes",
            channel=channel,
            timestamp=event["ts"]
        )
    except Exception as e:
        print(f"⚠️ Failed to react to message: {e}")

    try:
        if event_type == "app_mention":
            if text.contains("<@U04L9AWRH4Z>"):
                text = text.replace("<@U04L9AWRH4Z>", "").strip()
            history_messages = []
            try:
                response = client.web_client.conversations_replies(
                    channel=channel,
                    ts=message_ts, 
                )

                if response.get("messages"):
                    history_messages = [
                        f"<@{msg['user']}>: {msg['text']}"
                        for msg in reversed(response["messages"]) 
                        if "user" in msg and "text" in msg
                    ]

            except Exception as e:
                print(f"⚠️ Failed to fetch thread history: {e}")

            context = "\n".join(history_messages)
            full_prompt = f"Thread history:\n{context}\n\nNew message from <@{user}>: {text}"
            response: RunResponse = agent.run(full_prompt)
            final_text = f">{text}\n<@{user}> {response.content.strip()}"

            client.web_client.chat_postMessage(
                channel=channel,
                text=final_text,
                thread_ts=thread_ts
            )

        elif event_type == "message" and channel_type == "im":
            print(f"📩 DM from <@{user}>: {text}")
            response: RunResponse = agent.run(text)
            client.web_client.chat_postMessage(
                channel=channel,
                text=response.content.strip(),
                thread_ts=thread_ts
            )

        else:
            print("ℹ️ Event type not supported.")

    except Exception as e:
        print(f"❌ Error in event handler: {e}")
        client.web_client.chat_postMessage(
            channel=channel,
            text="⚠️ Sorry, something went wrong while processing your request."
        )


# === Start Socket Mode connection ===
client.socket_mode_request_listeners.append(process)
print("🚀 Connecting to Slack via Socket Mode...")
client.connect()
Event().wait()


# https://benheathworkspace.slack.com/archives/C08L9AWRH4Z/p1743535083057059
