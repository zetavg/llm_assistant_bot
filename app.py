import os
import yaml
import fire
import logging
import threading

from llm_assistant_bot.config import Config, set_config
from llm_assistant_bot.slack_bot import get_slack_bot_app

app_dir = os.path.dirname(os.path.abspath(__file__))
default_config_path = os.path.join(app_dir, 'config.yaml')


def main(config_path: str = default_config_path):
    config_dict = read_yaml_config(config_path)
    if config_dict is None:
        print(f"Config file not found at {config_path}.")
        return

    set_config(config_dict)
    print(f"Config loaded from {config_path}.")

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

    slack_bot_app = get_slack_bot_app()

    def run_slack_bot():
        slack_bot_app.start(Config.slack_bot_port)

    bot_thread = threading.Thread(target=run_slack_bot)
    bot_thread.start()


def read_yaml_config(config_path: str):
    if not os.path.exists(config_path):
        return None

    print(f"Loading config from {config_path}...")
    with open(config_path, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


if __name__ == "__main__":
    fire.Fire(main)
