import os

from ..paths import app_dir


class ChromaDBConfig:
    persist_directory: str = os.path.join(app_dir, '.chromadb')

    embedding_function_type: str = 'openai'
    embedding_function_model_name: str = 'text-embedding-ada-002'
