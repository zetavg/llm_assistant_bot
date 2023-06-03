class AgentConfig:
    max_generate_tokens: int = 512
    max_execution_time: int = 180
    conversation_memory_max_token_limit: int = 200
    old_observation_max_token_limit: int = 100

    llm_type: str = 'openai'
    llm_model_name: str = 'text-davinci-003'
    conversation_memory_llm_type: str = 'openai'
    conversation_memory_llm_model_name: str = 'text-davinci-003'

    prompt_template: str = ''
    history_template: str = ''
