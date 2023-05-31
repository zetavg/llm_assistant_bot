import os
import yaml
import json
import fire
import logging

from slack_bolt import App
from slack_sdk.web import WebClient

from llm_assistant_bot.config import Config, set_config
from llm_assistant_bot.onboarding_tutorial import OnboardingTutorial

app_dir = os.path.dirname(os.path.abspath(__file__))
default_config_path = os.path.join(app_dir, 'config.yaml')


def main(config_path: str = default_config_path):
    config_dict = read_yaml_config(config_path)
    if config_dict is None:
        print(f"Config file not found at {config_path}.")
        return

    set_config(config_dict)
    print(f"Config loaded from {config_path}.")

    app = App(
        token=Config.slack_bot_user_oauth_token,
        signing_secret=Config.slack_signing_secret,
    )
    onboarding_tutorials_sent = {}

    def start_onboarding(user_id: str, channel: str, client: WebClient):
        # Create a new onboarding tutorial.
        onboarding_tutorial = OnboardingTutorial(channel)

        # Get the onboarding message payload
        message = onboarding_tutorial.get_message_payload()

        # Post the onboarding message in Slack
        response = client.chat_postMessage(**message)

        # Capture the timestamp of the message we've just posted so
        # we can use it to update the message after a user
        # has completed an onboarding task.
        onboarding_tutorial.timestamp = response["ts"]

        # Store the message sent in onboarding_tutorials_sent
        if channel not in onboarding_tutorials_sent:
            onboarding_tutorials_sent[channel] = {}
        onboarding_tutorials_sent[channel][user_id] = onboarding_tutorial

    # ================ Team Join Event =============== #
    # When the user first joins a team, the type of the event will be 'team_join'.
    # Here we'll link the onboarding_message callback to the 'team_join' event.

    # Note: Bolt provides a WebClient instance as an argument to the listener function
    # we've defined here, which we then use to access Slack Web API methods like conversations_open.
    # For more info, checkout: https://slack.dev/bolt-python/concepts#message-listening
    @app.event("team_join")
    def onboarding_message(event, client):
        """Create and send an onboarding welcome message to new users. Save the
        time stamp of this message so we can update this message in the future.
        """
        # Get the id of the Slack user associated with the incoming event
        user_id = event.get("user", {}).get("id")

        # Open a DM with the new user.
        response = client.conversations_open(users=user_id)
        channel = response["channel"]["id"]

        # Post the onboarding message.
        start_onboarding(user_id, channel, client)

    # ============= Reaction Added Events ============= #
    # When a users adds an emoji reaction to the onboarding message,
    # the type of the event will be 'reaction_added'.
    # Here we'll link the update_emoji callback to the 'reaction_added' event.
    @app.event("reaction_added")
    def update_emoji(event, client):
        """Update the onboarding welcome message after receiving a "reaction_added"
        event from Slack. Update timestamp for welcome message as well.
        """
        # Get the ids of the Slack user and channel associated with the incoming event
        channel_id = event.get("item", {}).get("channel")
        user_id = event.get("user")

        if channel_id not in onboarding_tutorials_sent:
            return

        # Get the original tutorial sent.
        onboarding_tutorial = onboarding_tutorials_sent[channel_id][user_id]

        # Mark the reaction task as completed.
        onboarding_tutorial.reaction_task_completed = True

        # Get the new message payload
        message = onboarding_tutorial.get_message_payload()

        # Post the updated message in Slack
        updated_message = client.chat_update(**message)

    # =============== Pin Added Events ================ #
    # When a users pins a message the type of the event will be 'pin_added'.
    # Here we'll link the update_pin callback to the 'pin_added' event.
    @app.event("pin_added")
    def update_pin(event, client):
        """Update the onboarding welcome message after receiving a "pin_added"
        event from Slack. Update timestamp for welcome message as well.
        """
        # Get the ids of the Slack user and channel associated with the incoming event
        channel_id = event.get("channel_id")
        user_id = event.get("user")

        # Get the original tutorial sent.
        onboarding_tutorial = onboarding_tutorials_sent[channel_id][user_id]

        # Mark the pin task as completed.
        onboarding_tutorial.pin_task_completed = True

        # Get the new message payload
        message = onboarding_tutorial.get_message_payload()

        # Post the updated message in Slack
        updated_message = client.chat_update(**message)

    # ============== Message Events ============= #
    # When a user sends a DM, the event type will be 'message'.
    # Here we'll link the message callback to the 'message' event.
    @app.event("message")
    def message(event, client):
        """Display the onboarding welcome message after receiving a message
        that contains "start".
        """
        bot_info = client.auth_test()
        bot_id = bot_info["user_id"]

        channel_id = event.get("channel")
        user_id = event.get("user")
        text = event.get("text")
        message_ts = event.get("ts")
        # If message is not in a thread, thread_ts will be None.
        thread_ts = event.get("thread_ts", message_ts)

        # Check if this is a direct message by checking if the channel ID starts with 'D'
        if not channel_id.startswith('D'):
            # In channels, do not reply if the bot isn't mentioned.
            if f"<@{bot_id}>" not in text:
                return

        thread_replies = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts
        )

        print('--------')
        print('thread_replies', thread_replies)
        print('--------')

        users_info_cache = {}

        def get_user_info(user_id):
            if user_id not in users_info_cache:
                users_info_cache[user_id] = client.users_info(user=user_id)
                print('got', users_info_cache[user_id])
            return users_info_cache[user_id]

        history = []
        for message in thread_replies['messages']:
            if 'bot_id' in message:
                if message['user'] == bot_id:
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

        print('--------')
        print('history', json.dumps(history, indent=2, ensure_ascii=False))
        print('--------')

        if text and text.lower() == "start":
            return start_onboarding(user_id, channel_id, client)
        elif text:
            return client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,  # To reply in a thread
                text=f"I received a message from you! You said:\n> {text}",
            )

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    app.start(Config.port)


def read_yaml_config(config_path: str):
    if not os.path.exists(config_path):
        return None

    print(f"Loading config from {config_path}...")
    with open(config_path, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


if __name__ == "__main__":
    fire.Fire(main)
