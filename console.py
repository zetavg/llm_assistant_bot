from typing import Optional

import fire
from IPython import embed

from llm_assistant_bot.initialization import initialize
from llm_assistant_bot.config import Config as Config
from llm_assistant_bot.db import (
    chromadb_client as chromadb_client,
    add_memory as add_memory,
    query_memory as query_memory,
    delete_memory as delete_memory,
)


def main(config_path: Optional[str] = None):
    initialize(config_path=config_path)

    print("Welcome to the LLM Assistant Bot console!")
    print()
    print("query_memory, add_memory, delete_memory")
    embed(colors='neutral')


if __name__ == "__main__":
    fire.Fire(main)
