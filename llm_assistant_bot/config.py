from typing import Any, Dict


class Config:
    """
    Stores the application configuration. This is a singleton class.
    """

    timezone: str = 'Atlantic/Reykjavik'

    openai_api_key: str = ''

    agent_max_execution_time: int = 30

    slack_bot_port: int = 3000

    slack_bot_user_oauth_token: str = ''
    slack_signing_secret: str = ''


def set_config(config_dict: Dict[str, Any]):
    for key, value in config_dict.items():
        if not hasattr(Config, key):
            available_keys = [k for k in vars(
                Config) if not k.startswith('__')]
            raise ValueError(
                f"Invalid config key '{key}' in config. Available keys: {', '.join(available_keys)}.")
        setattr(Config, key, value)
