import os
from dotenv import load_dotenv
from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

from agno.agent import Agent, RunResponse
from agno.tools.slack import SlackTools
from agno.models.openai import OpenAIChat
from agno.utils.pprint import pprint_run_response
from agno.tools.jira import JiraTools
import requests

# === Load environment ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # xapp-...
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # xapp-...

# === Slack SDK Setup ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

# Fetch bot user ID dynamically from Slack
response = web_client.auth_test()
BOT_USER_ID = response["user_id"]

# === Agent Setup ===
slack_tools = SlackTools()
jira_tools = JiraTools()

agent = Agent(
    name="Reggie",
    model=OpenAIChat(id="gpt-4o"),
    tools=[slack_tools, jira_tools],
    show_tool_calls=True,
    instructions="If translating, return only the translated text."
)

# === Subscription Check (stubbed function) ===
def has_valid_subscription(team_id: str) -> bool:
    # TODO: Replace this stub with actual DB lookup
    # For example: query your database to see if team_id is valid
    VALID_TEAM_IDS = {"T06LP8F3K8V", "T87654321"}  # Example placeholder
    return team_id in VALID_TEAM_IDS

# def has_valid_subscription(slack_team_id: str) -> bool:
#     try:
#         workspace = SlackWorkspace.objects.get(slack_team_id=slack_team_id)
#         team = workspace.team
#         return team.subscriptions.filter(status="active").exists()
#     except SlackWorkspace.DoesNotExist:
#         return False

# === Process Slack Events ===
def process(client: SocketModeClient, req: SocketModeRequest):
    print("📥 Incoming request:", req.type)

    # Assign req to another variable for clarity (optional)
    request_data = req  # This now holds the original request data

    # Maybe add Try here
    # Acknowledge the event immediately
    if request_data.type == "events_api":
        handle_events_api(req)

        # Acknowledge the event immediately
    if request_data.type == "slash_commands":
        handle_slash_command(req)

    # OLD METHOD
    # if event_type == "app_mention":
    #     bot_user_id = req.payload["authorizations"][0]["user_id"]
    #     mention = f"<@{bot_user_id}>"
    #     cleaned_text = text.replace(mention, "").strip()

    # elif event_type == "events_api":
    #     bot_user_id = req.payload["authorizations"][0]["user_id"]
    #     mention = f"<@{bot_user_id}>"
    #     cleaned_text = text.replace(mention, "").strip()
    # elif event_type == "message" and channel_type == "im":
    #     cleaned_text = text.strip()


# # This works for slash_commands
#     payload = req.payload
#     print(payload)

#     # Extract workspace ID
#     team_id = payload.get("team_id")
#     print(f"🏢 Workspace ID (team_id): {team_id}")
#     # Access the relevant details from the payload
#     command = payload.get("command")  # This is the slash command, e.g., '/indo'
#     print(f"👤 Command: {command}")
#     text = payload.get("text")  # The text following the slash command (e.g., 'hey you')
#     print(f"💬 Message: {text}")
#     event_type = req.type
#     print(f"🔍 Event Type: {event_type}") # | ")
#     channel_type = req.channel_type
#     print(f"🔍 Channel Type: {channel_type}")
#     user_id = payload.get("user_id")  # User ID who issued the command
#     print(f"👤 User: {user_id}")
#     channel_id = payload.get("channel_id")  # Channel ID where the command was issued
#     response_url = payload.get("response_url")  
#     print(f"📡 Channel: {channel_id}")

#     # 1. Send the "Processing..." message via response_url for immediate acknowledgment
#     initial_response = {
#         "text": "⚙️ Processing... Please wait."
#     }
#     # Send the immediate acknowledgment back to Slack using the response URL
#     requests.post(response_url, json=initial_response)

#     # Clean text
#     if event_type == "app_mention":
#         bot_user_id = req.payload["authorizations"][0]["user_id"]
#         mention = f"<@{bot_user_id}>"
#         cleaned_text = text.replace(mention, "").strip()
#     elif event_type == "events_api":
#         bot_user_id = req.payload["authorizations"][0]["user_id"]
#         mention = f"<@{bot_user_id}>"
#         cleaned_text = text.replace(mention, "").strip()
#     elif event_type == "message" and channel_type == "im":
#         cleaned_text = text.strip()
    
#     elif req.type == "slash_commands":
#         print("Event")
#         handle_slash_command(req)
#     #elif req.type == "interactive":
#     #    handle_interactive(req)
#     else:
#         print("ℹ️ Unsupported event type, skipping.")
#         return

#     try:
#         print("\n🧠 Running agent with prompt:")
#         #agent.print_response(prompt, markdown=True)
#         print("⏳ Waiting for response...\n")

#         # Run the agent
#         response: RunResponse = agent.run(prompt)
#         final_text = f">From: <@{user_id}>\n>{text.strip()}\n```{response.content.strip()}\n```"
#         #print(final_text)
#         # Strip bot user mention from the final message text
#         final_text = final_text.replace(f"<@{BOT_USER_ID}>", "").strip()
#         #print("📤 Response:", final_text)

#         # Send reply to Slack with Markdown formatting
#         client.web_client.chat_postMessage(
#             channel=channel,
#             text=final_text
#         )


    # except Exception as e:
    #     print(f"❌ Error while processing prompt: {e}")
    #     client.web_client.chat_postMessage(
    #         channel=channel,
    #         text="⚠️ Sorry, something went wrong while processing your request."
    #     )

# === Handle Slash Commands ===
def handle_slash_command(req: SocketModeRequest):
    # Send acknowledgment response to Slack to avoid timeout
    # Acknowledge the event
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    # Add a reaction to the message (e.g., "eyes" emoji) as an acknowledgment in the channel
    event = req.payload.get("event", {})
    if event:
        client.web_client.reactions_add(
            name="eyes",
            channel=event["channel"],  # Channel where the event occurred
            timestamp=event["ts"],  # Timestamp of the message that triggered the event
        )

    # Extract slash command payload
    command = req.payload.get("command")
    text = req.payload.get("text")  # The text part after the slash command
    user_id = req.payload.get("user_id")
    channel_id = req.payload.get("channel_id")

    print(f"Received slash command: {command}")
    print(f"Command text: {text}")
    

    if command == "/indo":
        # Translate the text (remove '/indo' and translate the rest)
        text_to_translate = text.strip()
        prompt = f"Translate this message to Indonesian: {text_to_translate}"

        try:
            # Run the agent to get the translation
            response: RunResponse = agent.run(prompt)
            translation = response.content.strip()

            # Send back the translated text to Slack
            final_text = f">From: <@{user_id}>\n>{text}\n```{translation}```"
            web_client.chat_postMessage(
                channel=channel_id,
                text=final_text
            )

        # Move this exception higher
        except Exception as e:
            print(f"❌ Error processing slash command: {e}")
            web_client.chat_postMessage(
                channel=channel_id,
                text="⚠️ Sorry, something went wrong while processing your translation request."
            )
    if command == "/en":
        # Translate the text (remove '/indo' and translate the rest)
        text_to_translate = text.strip()
        prompt = f"Translate this message to English: {text_to_translate}"

        try:
            # Run the agent to get the translation
            response: RunResponse = agent.run(prompt)
            translation = response.content.strip()

            # Send back the translated text to Slack
            final_text = f">From: <@{user_id}>\n>{text}\n```{translation}```"
            web_client.chat_postMessage(
                channel=channel_id,
                text=final_text
            )

        # Move this exception higher
        except Exception as e:
            print(f"❌ Error processing slash command: {e}")
            web_client.chat_postMessage(
                channel=channel_id,
                text="⚠️ Sorry, something went wrong while processing your translation request."
            )
        


# === Handle Events API ===
def handle_events_api(req: SocketModeRequest):
    # Send acknowledgment response to Slack to avoid timeout
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    # Add a reaction to the message (e.g., "eyes" emoji) as an acknowledgment in the channel
    event = req.payload.get("event", {})
    if event:
        client.web_client.reactions_add(
            name="eyes",
            channel=event["channel"],  # Channel where the event occurred
            timestamp=event["ts"],  # Timestamp of the message that triggered the event
        )

        # Now, access various properties inside the event dictionary
        event_type = event.get("type")  # e.g., app_mention
        print("Event Type:", event_type)
    
        # Clean text from the mention if it's an app mention
        if event_type == "app_mention":
            bot_user_id = req.payload["authorizations"][0]["user_id"]  # Get bot's user ID
            user = event.get("user")
            # Extract workspace ID
            team_id = req.payload.get("team_id")
            mention = f"<@{bot_user_id}>"
            text = event.get("text", "")  # Make sure the text is safely retrieved
            channel = event.get("channel")
            cleaned_text = text.replace(mention, "").strip()  # Clean the mention from the text

            print(f"🏢 Workspace ID (team_id): {team_id}")
            print(f"Bot User ID: {bot_user_id}")
            print(f"Mention: {mention}")
            print(f"User:", user)
            print(f"Cleaned Text: {cleaned_text}")
            print(f"Channel:", channel)

            print("\n🧠 Running agent with prompt:")
            print("⏳ Checking for valid Subscription\n")
            # Check for valid subscription
            if not has_valid_subscription(team_id):
                print("🚫 Unauthorized workspace.")
                channel = req.payload.get("event", {}).get("channel")
                if channel:
                    client.web_client.chat_postMessage(
                        channel=channel,
                        text="⚠️ This workspace does not have an active subscription."
                    )
                return

            try:
                prompt = cleaned_text
                # Run the agent
                response: RunResponse = agent.run(prompt)
                #final_text = f">From: <@{user}>\n>{text.strip()}\n```{response.content.strip()}\n```"
                final_text = f">{text.strip()}\n<@{user}> {response.content.strip()}\n"
                
                #print(final_text)
                # Strip bot user mention from the final message text
                final_text = final_text.replace(f"<@{BOT_USER_ID}>", "").strip()
                #print("📤 Response:", final_text)

                # Send reply to Slack with Markdown formatting
                client.web_client.chat_postMessage(
                    channel=channel,
                    text=final_text
                )
            except Exception as e:
                print(f"❌ Error while processing prompt: {e}")
                client.web_client.chat_postMessage(
                    channel=channel,
                    text="⚠️ Sorry, something went wrong while processing your request."
                )

# === Register and Connect ===
client.socket_mode_request_listeners.append(process)
print("🚀 Connecting to Slack via Socket Mode...")
client.connect()

# === Keep alive ===
from threading import Event
Event().wait()
