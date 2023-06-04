import typing
from typing import Type, Any, Dict

from .agent_config import AgentConfig
from .chromadb_config import ChromaDBConfig
from .slack_config import SlackConfig


class Config:
    """
    Stores the application configuration. This is a singleton class.
    """

    timezone: str = 'Atlantic/Reykjavik'

    openai_api_key: str = ''

    log_level: str = 'info'

    agent: Type[AgentConfig] = AgentConfig
    chromadb: Type[ChromaDBConfig] = ChromaDBConfig
    slack: Type[SlackConfig] = SlackConfig


def set_config(config_dict: Dict[str, Any], target=Config, key_prefix=''):
    type_hints = typing.get_type_hints(target)
    for key, value in config_dict.items():
        if key not in type_hints:
            available_keys = [k for k in type_hints]
            raise ValueError(
                f"Invalid config key '{key_prefix}{key}' in config. Available keys: {', '.join(available_keys)}.")

        type_hint = type_hints[key]

        if (
            type_hint.__module__ not in ['builtins', 'typing']
            or getattr(type_hint, '__origin__', None) is type
        ):
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(
                    f"Expect type for config '{key_prefix}{key}' to be dict, got '{type(value)}'.")
            set_config(value, getattr(target, key), f'{key_prefix}{key}.')
            continue

        elif not isinstance(value, type_hints[key]):
            raise TypeError(
                f"Invalid type for config '{key_prefix}{key}': Expected '{type_hints[key]}', got '{type(value)}'.")

        setattr(target, key, value)
