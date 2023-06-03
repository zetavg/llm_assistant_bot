class AgentConfig:
    max_execution_time: int = 180
    memory_k: int = 12

    llm_type: str = 'openai'
    llm_model_name: str = 'text-davinci-003'

    prompt_template: str = ''
    history_template: str = ''
