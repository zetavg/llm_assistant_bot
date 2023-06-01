import json
import logging

from slack_bolt import App
from slack_sdk.web import WebClient

from ..config import Config

TYPING_MESSAGE_TEXT = "_(typing...)_"


def get_slack_bot_app():
    logger = logging.getLogger("slack_bot")
    cached_bot_info = None

    def get_bot_info(client: WebClient):
        nonlocal cached_bot_info
        if cached_bot_info is None:
            cached_bot_info = client.auth_test()
        return cached_bot_info

    app = App(
        token=Config.slack_bot_user_oauth_token,
        signing_secret=Config.slack_signing_secret,
    )

    @app.event("reaction_added")
    def reaction_added(event, client: WebClient):
        pass

    @app.event("message")
    def message(event, client: WebClient):
        if 'bot_id' in event:
            return

        if 'subtype' in event:
            subtype = event['subtype']
            if subtype == 'message_changed':
                return

        bot_info = get_bot_info(client)
        bot_id = bot_info["user_id"]

        channel_id = event.get("channel")
        user_id = event.get("user")
        text = event.get("text")
        message_ts = event.get("ts")
        # If message is not in a thread, thread_ts will be None.
        thread_ts = event.get("thread_ts", message_ts)

        is_direct_message = True

        # Check if this is a direct message by checking if the channel ID starts with 'D'
        if not channel_id.startswith('D'):
            is_direct_message = False
            # In channels or group direct messages, do not reply if the bot
            # isn't mentioned.
            if f"<@{bot_id}>" not in text:
                return

        typing_message = client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,  # Should always reply in the thread.
            text=TYPING_MESSAGE_TEXT,
        )

        try:
            thread_replies = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )

            # print('--------')
            # print('thread_replies', thread_replies)
            # print('--------')

            user_info_cache = {}

            def get_user_info(user_id):
                if user_id not in user_info_cache:
                    user_info_cache[user_id] = client.users_info(user=user_id)
                return user_info_cache[user_id]

            history = []
            for message in thread_replies.get('messages', []):
                if 'bot_id' in message:
                    if (
                        message['user'] == bot_id
                        and message['text'] != TYPING_MESSAGE_TEXT
                    ):
                        history.append({
                            'from': 'bot',
                            'message': message['text']
                        })
                    # Messages not from this bot are ignored.
                else:
                    user_info = get_user_info(message['user'])
                    history.append({
                        'from': 'user',
                        'user_id': message['user'],
                        # 'user_id': user_info['user']['id'],
                        'user_name': user_info['user']['real_name'],
                        # 'user_display_name': user_info['user']['profile']['display_name'],
                        'message': message['text'],
                    })

            logger.debug(
                '---- thread history:\n%s\n---- end of thread history ----',
                json.dumps(history, indent=2, ensure_ascii=False)
            )

            reply = f"I received a message from you! You said:\n> {text}"

            if not is_direct_message:
                reply = f"<@{user_id}> {reply}"

            return client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,  # Should always reply in the thread.
                text=reply,
            )
        except Exception as e:
            exception = Exception(
                str(e) + f'. Event: {str(event)}'
            )
            raise exception from e
        finally:
            client.chat_delete(
                channel=channel_id,
                ts=typing_message.get('ts', ''),
            )

    return app
