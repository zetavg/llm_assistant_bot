from langchain.llms import OpenAI

from .config import Config

llm = OpenAI(openai_api_key=Config.openai_api_key)  # type: ignore
