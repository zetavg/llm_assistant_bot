from typing import Any, Union, Callable

import re
import logging
import datetime
import pytz

from langchain import BasePromptTemplate, OpenAI, LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.agents import (
    AgentExecutor, Tool, LLMSingleActionAgent, AgentOutputParser
)
from langchain.prompts import StringPromptTemplate
from langchain.schema import AgentAction, AgentFinish
from langchain.memory import ConversationSummaryBufferMemory, ConversationBufferWindowMemory
from langchain.utilities import PythonREPL
import tiktoken

from ..config import Config
from ..db import query_memory
from .tools.memory import get_memory_tools, get_memories_text
from .tools.docs import get_docs_tools
from .tools.python_repl import get_python_repl_tool
from .tools.web_browsing import get_browser_tools

logger = logging.getLogger("agent")


def get_llm(model_type, model_name):
    if model_type == 'openai':
        if model_name in ['gpt-4', 'gpt-4-32k']:
            return ChatOpenAI(
                model=model_name,
                temperature=0,
                max_tokens=Config.agent.max_generate_tokens,
            )  # type: ignore
        elif model_name == 'text-davinci-003':
            return OpenAI(
                model='text-davinci-003',
                temperature=0,
                max_tokens=Config.agent.max_generate_tokens,
            )  # type: ignore
        else:
            raise ValueError(
                f'Invalid LLM model name: {model_name}')
    else:
        raise ValueError(f'Invalid LLM type: {model_type}')


def get_llm_max_token_limit(model_type, model_name):
    if model_type == 'openai':
        if model_name == 'gpt-4':
            return 8192
        elif model_name == 'text-davinci-003':
            return 4096
        else:
            raise ValueError(
                f'Invalid LLM model name: {model_name}')
    else:
        raise ValueError(f'Invalid LLM type: {model_type}')


def get_llm_tokenizer(model_type, model_name):
    if model_type == 'openai':
        return tiktoken.encoding_for_model(model_name)
    else:
        raise ValueError(f'Invalid LLM type: {model_type}')


class Agent():
    def __init__(
        self,
        use_tool_callback: Union[Callable[[str, Any], Any], None] = None
    ):
        self.llm = get_llm(Config.agent.llm_type, Config.agent.llm_model_name)
        self.llm_max_token_limit = get_llm_max_token_limit(
            Config.agent.llm_type, Config.agent.llm_model_name
        )
        self.tokenizer = get_llm_tokenizer(
            Config.agent.llm_type, Config.agent.llm_model_name
        )
        llm_max_token_limit = self.llm_max_token_limit
        tokenizer = self.tokenizer

        # Setup tools
        browser_tools = get_browser_tools()
        python_repl_tool = get_python_repl_tool()

        self.tools = [
            *get_memory_tools(tokenizer=tokenizer),
            *get_docs_tools(tokenizer=tokenizer),
            python_repl_tool,
        ] + browser_tools
        self.tool_names = [tool.name for tool in self.tools]
        self.use_tool_callback = use_tool_callback

        tools = self.tools
        use_tool_callback = self.use_tool_callback

        # Setup prompt template
        class PromptTemplate(StringPromptTemplate):
            def format(self, **kwargs) -> str:
                prompt_template = Config.agent.prompt_template

                timezone = pytz.timezone(Config.timezone)
                local_time = datetime.datetime.now(timezone)
                date_str = local_time.strftime('%Y-%m-%d')

                # Get the intermediate steps (AgentAction, Observation tuples)
                # Format them in a particular way
                intermediate_steps = kwargs.pop("intermediate_steps")
                intermediate_steps_len = len(intermediate_steps)
                thoughts = ""
                for i, (action, observation) in enumerate(intermediate_steps):
                    thoughts += action.log
                    if i < intermediate_steps_len - 1:
                        tokenized_observation = tokenizer.encode(observation)
                        if len(tokenized_observation) > Config.agent.old_observation_max_token_limit:
                            observation = tokenizer.decode(tokenized_observation[:Config.agent.old_observation_max_token_limit]) + \
                                '\n  ... (observation content truncated)'
                    thoughts += f"\nObservation: {observation}\nThought: "
                # Set the agent_scratchpad variable to that value
                kwargs["agent_scratchpad"] = thoughts
                # Create a tools variable from the list of tools provided
                kwargs["tools"] = "\n".join(
                    [f"{tool.name}: {tool.description}" for tool in tools])
                # Create a list of tool names for the tools provided
                kwargs["tool_names"] = ", ".join([tool.name for tool in tools])

                kwargs["current_date"] = date_str
                kwargs["knowledge_cutoff_date"] = '2021-01-01'
                kwargs["timezone"] = Config.timezone

                kwargs['memories'] = get_memories_text(
                    kwargs['input'],
                    tokenizer=tokenizer,
                )

                if not kwargs['memories']:
                    kwargs['memories'] = ''
                elif Config.agent.memories_template:
                    kwargs['memories'] = \
                        Config.agent.memories_template.format(**kwargs) + '\n'

                if not kwargs.get('history'):
                    kwargs['history'] = ''
                elif Config.agent.history_template:
                    kwargs['history'] = \
                        Config.agent.history_template.format(**kwargs) + '\n'

                kwargs['pre_taken_actions'] = \
                    kwargs['memories']

                if kwargs['pre_taken_actions'] and Config.agent.pre_taken_actions_template:
                    kwargs['pre_taken_actions'] = \
                        Config.agent.pre_taken_actions_template.format(**kwargs) + '\n'

                prompt = prompt_template.format(**kwargs)

                tokenized_prompt = tokenizer.encode(prompt)
                token_limit = llm_max_token_limit - (Config.agent.max_generate_tokens + 20)
                prompt_truncated = False
                if len(tokenized_prompt) > token_limit:
                    tokenized_prompt_truncated = \
                        tokenized_prompt[:token_limit]
                    prompt = tokenizer.decode(tokenized_prompt_truncated)
                    prompt += '\n  ... (truncated)\nThought:'
                    prompt_truncated = True

                if prompt_truncated:
                    logger.info(f"Prompt length (truncated): {len(tokenized_prompt_truncated)} tokens (original: {len(tokenized_prompt)}) tokens")
                else:
                    logger.info(f"Prompt length: {len(tokenized_prompt)} tokens")

                if kwargs.get('agent_scratchpad'):
                    logger.debug(
                        f"Current prompt:\n---- BEGIN OF PROMPT ----\n{prompt}\n---- END OF PROMPT ----")
                else:
                    logger.info(
                        f"Initial prompt:\n---- BEGIN OF PROMPT ----\n{prompt}\n---- END OF PROMPT ----")

                return prompt

        self.prompt_template = PromptTemplate(
            # This omits the `agent_scratchpad`, `tools`, and `tool_names` variables because those are generated dynamically
            # This includes the `intermediate_steps` variable because that is needed
            input_variables=["input", "intermediate_steps", "history"],
        )

        class OutputParser(AgentOutputParser):
            def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
                # Check if agent should finish
                if "Final Reply:" in llm_output:
                    return AgentFinish(
                        # Return values is generally always a dictionary with a single `output` key
                        # It is not recommended to try anything else at the moment :)
                        return_values={"output": llm_output.split(
                            "Final Reply:")[-1].strip()},
                        log=llm_output,
                    )
                # Parse out the action and action input
                regex = r"Action\s*\d*\s*:(.*?)(?:\nAction\s*\d*\s*Input\s*\d*\s*:[\s]*(.*))?$"
                match = re.search(regex, llm_output, re.DOTALL)
                if not match:
                    # raise ValueError(
                    #     f"Could not parse LLM output: `{llm_output}`")
                    return AgentFinish(
                        # Return values is generally always a dictionary with a single `output` key
                        # It is not recommended to try anything else at the moment :)
                        return_values={"output": llm_output.strip()},
                        log=llm_output,
                    )
                action = match.group(1).strip()
                action_input = match.group(2) or ''

                tool_input = action_input.strip(" ").strip('"')
                if use_tool_callback:
                    use_tool_callback(action, tool_input)

                return AgentAction(
                    tool=action,
                    tool_input=tool_input,
                    log=llm_output
                )

        self.output_parser = OutputParser()

        # LLM chain consisting of the LLM and a prompt
        self.llm_chain = LLMChain(
            llm=self.llm,
            prompt=self.prompt_template,
        )

        self.agent = LLMSingleActionAgent(
            llm_chain=self.llm_chain,
            output_parser=self.output_parser,
            stop=["\nObservation:"],
            allowed_tools=self.tool_names,  # type: ignore
        )

    def get_agent_executor(self, memory: ConversationSummaryBufferMemory):
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            memory=memory,
            max_execution_time=Config.agent.max_execution_time,
        )
        return agent_executor

    def get_new_memory(self):
        llm = get_llm(
            Config.agent.conversation_memory_llm_type,
            Config.agent.conversation_memory_llm_model_name,
        )
        return ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=Config.agent.conversation_memory_max_token_limit,
        )
