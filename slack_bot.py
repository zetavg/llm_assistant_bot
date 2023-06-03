from typing import Optional

import fire

from llm_assistant_bot.initialization import initialize
from llm_assistant_bot.config import Config
from llm_assistant_bot.slack_bot import get_slack_bot_app

import nest_asyncio
nest_asyncio.apply()


def main(config_path: Optional[str] = None):
    initialize(config_path=config_path)

    slack_bot_app = get_slack_bot_app()
    slack_bot_app.start(
        host=Config.slack.bot_host,
        port=Config.slack.bot_port,
    )


if __name__ == "__main__":
    fire.Fire(main)
