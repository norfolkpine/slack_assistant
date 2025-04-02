import json
import os
from typing import Any, Dict, List, Optional

from agno.tools.toolkit import Toolkit
from agno.utils.log import logger
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode import SocketModeClient

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    raise ImportError("Slack tools require the `slack_sdk` package. Run `pip install slack-sdk` to install it.")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

class SlackTools(Toolkit):
    def __init__(
        self,
        token: Optional[str] = None,
        event: Optional[Dict[str, Any]] = None,
        send_message: bool = True,
        list_channels: bool = True,
        get_thread_history: bool = True,
        get_current_channel: bool = True,
        get_previous_user_message: bool = True,
    ):
        super().__init__(name="slack")
        self.token: Optional[str] = token or os.getenv("SLACK_TOKEN")
        self.event: Optional[Dict[str, Any]] = event  # 👈 save it here
        
        if self.token is None or self.token == "":
            raise ValueError("SLACK_TOKEN is not set")
        web_client = WebClient(token=SLACK_BOT_TOKEN)
        self.client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

        if send_message:
            self.register(self.send_message)
        if list_channels:
            self.register(self.list_channels)
        if get_thread_history:
            self.register(self.get_chat_thread_history)
        if get_current_channel:
            self.register(self.get_current_channel)
        if get_previous_user_message:
            self.register(self.get_previous_user_message)

    def current_request(self,  req: SocketModeRequest) -> None:
        self.req = req
        self._set_event(req.payload.get("event"))

    def _set_event(self, event: Dict[str, Any]) -> None:
        if self.event is not None:
            return
        
        self.event = {
            "channel": event.get("channel"),
            "ts": event.get("ts")
        }

    def send_message(self, reply_to_user: str, channel: str, text: str, thread_ts: Optional[str] = None) -> str:
        try:
            final_text = f"<@{reply_to_user}> {text}" if reply_to_user else text
            response = self.client.web_client.chat_postMessage(
                channel=channel, 
                text=final_text,
                thread_ts=thread_ts,
            )
            return json.dumps(response.data)
        except SlackApiError as e:
            logger.error(f"Error sending message: {e}")
            return json.dumps({"error": str(e)})

    def list_channels(self) -> str:
        try:
            response = self.client.web_client.conversations_list()
            channels = [{"id": channel["id"], "name": channel["name"]} for channel in response["channels"]]
            return json.dumps(channels)
        except SlackApiError as e:
            logger.error(f"Error listing channels: {e}")
            return json.dumps({"error": str(e)})

    def get_chat_thread_history(self, channel: str, thread_ts: Optional[str] = None, limit: int = 100) -> str:
        try:
            if thread_ts:
                # Get thread replies if thread_ts is provided
                response = self.client.web_client.conversations_replies(
                    channel=channel,
                    ts=thread_ts,
                    limit=limit
                )
                messages: List[Dict[str, Any]] = [
                    {
                        "text": msg.get("text", ""),
                        "user": "webhook" if msg.get("subtype") == "bot_message" else msg.get("user", "unknown"),
                        "ts": msg.get("ts", ""),
                        "sub_type": msg.get("subtype", "unknown"),
                        "attachments": msg.get("attachments", []) if msg.get("subtype") == "bot_message" else "n/a",
                    }
                    for msg in response.get("messages", [])
                ]
            else:
                # Get normal conversation history
                response = self.client.web_client.conversations_history(channel=channel, limit=limit)
                messages: List[Dict[str, Any]] = [
                    {
                        "text": msg.get("text", ""),
                        "user": "webhook" if msg.get("subtype") == "bot_message" else msg.get("user", "unknown"),
                        "ts": msg.get("ts", ""),
                        "sub_type": msg.get("subtype", "unknown"),
                        "attachments": msg.get("attachments", []) if msg.get("subtype") == "bot_message" else "n/a",
                    }
                    for msg in response.get("messages", [])
                ]
            return json.dumps(messages)
        except SlackApiError as e:
            logger.error(f"Error getting channel history: {e}")
            return json.dumps({"error": str(e)})

    def get_current_channel(self) -> str:
        """
        Fallback method to guess the current channel (e.g., most recently active public one).

        Returns:
            str: JSON with the guessed current channel name and ID.
        """
        try:
            response = self.client.web_client.conversations_list(types="public_channel,private_channel", exclude_archived=True)
            channels = response.get("channels", [])
            if not channels:
                return json.dumps({"error": "No channels found"})

            # Example: return first channel (or enhance logic)
            most_recent = channels[0]
            return json.dumps({
                "id": most_recent["id"],
                "name": most_recent["name"]
            })

        except SlackApiError as e:
            logger.error(f"Error listing channels: {e}")
            return json.dumps({"error": str(e)})


    def get_previous_user_message(self, event: Optional[Dict[str, Any]] = None, limit: int = 20) -> str:
        """
        Get the previous user message from the same channel.

        Args:
            event (Dict[str, Any], optional): Slack event with 'channel' key. If None, uses self.event.
            limit (int): How many messages to look back.

        Returns:
            str: The most recent human message before the current one.
        """
        try:
            # Use the stored event if none provided
            if event is None:
                event = self.event
                
            if not event:
                return json.dumps({"error": "No event data available."})
            
            channel = event.get("channel")
            current_ts = event.get("ts")

            if not channel:
                return json.dumps({"error": "Channel ID not found in event."})
            
            response = self.client.conversations_history(channel=channel, limit=limit)
            messages = response.get("messages", [])

            for msg in messages:
                if msg.get("ts") == current_ts:
                    continue  # skip the current message
                if msg.get("subtype") == "bot_message":
                    continue  # skip bots
                if "user" in msg and msg.get("text"):
                    return json.dumps({
                        "text": msg["text"],
                        "user": msg["user"],
                        "ts": msg["ts"]
                    })

            return json.dumps({"error": "No previous user message found."})
        except SlackApiError as e:
            logger.error(f"Slack API error: {e}")
            return json.dumps({"error": str(e)})
        except Exception as e:
            logger.error(f"Error getting previous message: {e}")
            return json.dumps({"error": str(e)})
