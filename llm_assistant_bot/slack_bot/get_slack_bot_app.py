import re
import json
import logging
import asyncio
import time

from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from langchain.memory import ConversationBufferWindowMemory
import commonmarkslack

from ..agent import Agent

from ..config import Config

TYPING_MESSAGE_TEXT = "_(thinking...)_"


# def convert_markdown_to_slack(text):
#     # commonmarkslack will make content in code fences disappear.
#     # So we replace code fences with a temporary placeholder.
#     text = text.replace('```', '程式碼\x1f區塊')
#     parser = commonmarkslack.Parser()
#     ast = parser.parse(text)
#     renderer = commonmarkslack.SlackRenderer()
#     slack_md = renderer.render(ast)

#     # Replace the temporary placeholder back with code fences.
#     slack_md = slack_md.replace('程式碼\x1f區塊', '```')
#     return slack_md

def _convert_markdown_to_slack(text):
    parser = commonmarkslack.Parser()
    ast = parser.parse(text)
    renderer = commonmarkslack.SlackRenderer()
    slack_md = renderer.render(ast)
    return slack_md


def convert_markdown_to_slack(text):
    texts = text.split('```')
    # Do not convert markdown in code fences.
    texts = [
        _convert_markdown_to_slack(t) if i % 2 == 0 else t
        for i, t in enumerate(texts)]
    return '```'.join(texts)


def get_slack_bot_app():
    logger = logging.getLogger("slack_bot")

    # cached_agent = None

    # def get_agent() -> Agent:
    #     # nonlocal cached_agent
    #     # if cached_agent is None:
    #     #     cached_agent = Agent()
    #     # return cached_agent
    #     return Agent()

    cached_bot_info = None

    async def get_bot_info(client: AsyncWebClient):
        nonlocal cached_bot_info
        if cached_bot_info is None:
            cached_bot_info = await client.auth_test()
        return cached_bot_info

    app = AsyncApp(
        token=Config.slack_bot_user_oauth_token,
        signing_secret=Config.slack_signing_secret,
    )

    @app.event("reaction_added")
    async def reaction_added(event, client: AsyncWebClient):
        pass

    @app.event("message")
    async def message(event, client: AsyncWebClient):
        if 'bot_id' in event:
            return

        if 'subtype' in event:
            subtype = event['subtype']
            if subtype == 'message_changed':
                return

        bot_info = await get_bot_info(client)
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

        send_typing_message_task = asyncio.create_task(
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,  # Should always reply in the thread.
                text=TYPING_MESSAGE_TEXT,
            )
        )

        async def update_status_async(status):
            typing_message = await send_typing_message_task
            message_ts = typing_message['ts']
            return await client.chat_update(
                channel=channel_id,
                ts=message_ts,  # type: ignore
                text=f'_({status})_'
            )

        def update_status(status):
            return asyncio.create_task(
                update_status_async(status)
            )

        try:
            thread_replies = await client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )

            # print('--------')
            # print('thread_replies', thread_replies)
            # print('--------')

            user_info_cache = {}

            async def get_user_info(user_id):
                if user_id not in user_info_cache:
                    user_info_cache[user_id] = \
                        await client.users_info(user=user_id)
                return user_info_cache[user_id]

            history = []
            for message in thread_replies.get('messages', []):
                if message['ts'] == message_ts:
                    # Ignore the current message that triggered this event.
                    continue

                if 'bot_id' in message:
                    if (
                        message['user'] == bot_id
                        and not message['text'].startswith('_(')
                    ):
                        history.append({
                            'from': 'bot',
                            'message': message['text']
                        })
                    # Messages not from this bot are ignored.
                else:
                    user_info = await get_user_info(message['user'])
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

            memory = ConversationBufferWindowMemory(k=8)
            for h in history:
                if h['from'] == 'user':
                    memory.chat_memory.add_user_message(
                        f"@{h['user_name']}: " + h['message']
                    )
                if h['from'] == 'bot':
                    message = h['message']
                    message = re.sub(r'\n_\([^()]+\)_$', '', message)
                    message = message.strip()
                    memory.chat_memory.add_ai_message(message)

            def use_tool_callback(tool_name, input):
                if tool_name == 'python_repl':
                    update_status(f'Executing Python code...')
                elif tool_name == 'browser_google_search':
                    update_status(f'Searching "{input}" on Google...')
                elif tool_name == 'browser_navigate':
                    if len(input) > 40:
                        input = f"<{input[:40] + '...'}|{input}>"
                    update_status(f'Browsing "{input}"...')

            ai_started_at = time.time()
            agent = Agent(use_tool_callback=use_tool_callback)
            agent_executor = agent.get_agent_executor(
                memory=memory
            )

            user_info = await get_user_info(event['user'])
            user_name = user_info['user']['real_name']
            reply = await agent_executor.arun(
                f"@{user_name}: {text}"
            )
            ai_ended_at = time.time()
            # reply = f"I received a message from you! You said:\n> {text}"

            if not is_direct_message:
                reply = f"<@{user_id}> {reply}"

            reply_text = convert_markdown_to_slack(reply)

            reply_text += f"\n_(Model: {agent.llm.model_name}, time elapsed: {ai_ended_at - ai_started_at:.1f}s)_"

            return await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,  # Should always reply in the thread.
                text=reply_text,
                mrkdwn=True,
            )
        except Exception as e:
            exception = Exception(
                str(e) + f'. Event: {str(event)}'
            )
            error_message = str(e)
            if isinstance(e, asyncio.exceptions.TimeoutError):
                error_message = f"agent operation timeout (> {Config.agent_max_execution_time} seconds)"
            error_message = error_message.replace('\n', ' ')
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,  # Should always reply in the thread.
                text=f"_⚠ An error occurred: {error_message}_",
            )
            raise exception from e
        finally:
            typing_message = await send_typing_message_task
            await client.chat_delete(
                channel=channel_id,
                ts=typing_message.get('ts', ''),
            )

    return app
