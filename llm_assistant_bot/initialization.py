import os
import yaml
import logging

from .config import Config, set_config
from .paths import default_config_path


def initialize(config_path=None):
    if not config_path:
        config_path = default_config_path

    config_dict = read_yaml_config(config_path)

    if config_dict is None:
        raise ValueError(f"Config file not found at {config_path}.")

    set_config(config_dict)
    print(f"Config loaded from {config_path}.")

    logger = logging.getLogger()
    log_level_str = Config.log_level.upper()
    logger.setLevel(getattr(logging, log_level_str))
    logger.addHandler(logging.StreamHandler())
    print("Log level:", log_level_str)


def read_yaml_config(config_path: str):
    if not os.path.exists(config_path):
        return None

    print(f"Loading config from {config_path}...")
    with open(config_path, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config
