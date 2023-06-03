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
from langchain.memory import ConversationBufferWindowMemory
from langchain.utilities import PythonREPL

from ..config import Config
from ..tools.web_browsing import get_browser_tools

logger = logging.getLogger("agent")

template_without_history = """Here is a new message from the user:

```
{input}
```

Your name is AssistantGPT. As a professional assistant of the team, reply the message as best you can. You have access to the following tools:

{tools}

Use the following format:

```
Message: the input message you should answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times, and can be omitted if unnecessary)
Thought: I now know how to reply
Final Reply: the final reply to the original input message
```

If using a tool is not necessary, you can omit the Action/Action Input/Observation steps and go straight to the Final Reply, for example:

```
Message: Hi!
Thought: This is a friendly greeting, I should respond in kind
Thought: I now know how to reply
Final Reply: Hi there! How can I help you?
```

Every "Thought: ..." MUST be followed by a "Action: ..." or a "Final Reply: ...".

Here are some additional rules you should follow:

0. Do not make up any information. If you cannot find a confident answer from the conversation history or observation, you should amiably tell the user that you cannot find the answer.
1. If you are referencing any documents when making your reply, you should ALWAYS include the link to the document in the Final Reply.
1. You MUST use standard Markdown syntax when writing your reply. You MUST NOT follow the format in the conversation history. You MUST use the syntax `[text](url)` for links.
2. When being asked questions referring to a relative date, you MUST use an absolute date (based on the given current date) during your thought. Additionally, you MUST use absolute date when using tools (such as browser_google_search).
3. Use the same language as the user. If the user is using Chinese, prefer Traditional Chinese (Taiwanese Mandarin) over Simplified Chinese unless you are sure that the user is using Simplified Chinese.
4. Use whitespace between CJK (Chinese, Japanese, Korean) and half-width characters (alphabetical letters, numerical digits and symbols). For example, do not write: "當你凝視著bug，bug也凝視著你", do: "當你凝視著 bug，bug 也凝視著你".
5. You should not use the 'python_repl' tool if unnecessary. Use it only if you need to do something such as math calculation.
6. You MUST NOT use the 'python_repl' tool to execute code that is too complex or takes too long to run.
7. You MUST include the content of the final Reply in the Final Reply step, you MUST NOT ask the user to check elsewhere for the result.
8. When you are giving sample code to the user, you should place it in a markdown code block.

Begin!

{agent_scratchpad}"""

template = """```
{history}
```

Above is the conversation history between you (AI) and user(s) (Human). Note that the "Human" user might be different individuals, in such case, the user's name will be annotated in the message, such as: "Human: @username: This is the message from @username".

""" + template_without_history


class Agent():
    def __init__(
        self,
        use_tool_callback: Union[Callable[[str, Any], Any], None] = None
    ):
        # Setup tools
        browser_tools = get_browser_tools()

        python_repl = PythonREPL()
        async def python_repl_arun(command):
            return python_repl.run(command)
        python_repl_tool = Tool(
            name="python_repl",
            description="A Python shell. Use this to execute python commands. Input should be a valid python command. You must use `print(...)` in order to see the output. Do not use this if unnecessary.",
            func=python_repl.run,
            coroutine=python_repl_arun,
        )

        self.tools = [
            python_repl_tool,
        ] + browser_tools
        self.tool_names = [tool.name for tool in self.tools]
        self.use_tool_callback = use_tool_callback

        tools = self.tools
        use_tool_callback = self.use_tool_callback

        # Setup prompt template
        class PromptTemplate(StringPromptTemplate):
            def format(self, **kwargs) -> str:
                timezone = pytz.timezone(Config.timezone)
                local_time = datetime.datetime.now(timezone)
                date_str = local_time.strftime('%Y-%m-%d')

                # Get the intermediate steps (AgentAction, Observation tuples)
                # Format them in a particular way
                intermediate_steps = kwargs.pop("intermediate_steps")
                thoughts = ""
                for action, observation in intermediate_steps:
                    thoughts += action.log
                    thoughts += f"\nObservation: {observation}\nThought: "
                # Set the agent_scratchpad variable to that value
                kwargs["agent_scratchpad"] = thoughts
                # Create a tools variable from the list of tools provided
                kwargs["tools"] = "\n".join(
                    [f"{tool.name}: {tool.description}" for tool in tools])
                # Create a list of tool names for the tools provided
                kwargs["tool_names"] = ", ".join([tool.name for tool in tools])

                if not kwargs.get('history'):
                    kwargs_without_history = kwargs.copy()
                    kwargs_without_history.pop('history')
                    prompt = template_without_history.format(
                        **kwargs_without_history)
                else:
                    prompt = template.format(**kwargs)

                prompt = f"Current date: {date_str}\n\n" + prompt

                if kwargs.get('agent_scratchpad'):
                    logger.debug(
                        f"Current prompt:\n---- BEGIN OF PROMPT ----\n{prompt}\n---- END OF PROMPT ----")
                else:
                    logger.info(
                        f"Initial prompt:\n---- BEGIN OF PROMPT ----\n{prompt}\n---- END OF PROMPT ----")

                return prompt

        self.prompt_template = PromptTemplate(
            # template=template,
            # tools=tools,
            # # This omits the `agent_scratchpad`, `tools`, and `tool_names` variables because those are generated dynamically
            # # This includes the `intermediate_steps` variable because that is needed
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

        self.llm = ChatOpenAI(
            model='gpt-4',
            temperature=0
        )  # type: ignore
        # self.llm = OpenAI(
        #     model='text-davinci-003',
        #     temperature=0
        # )  # type: ignore

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

    def get_agent_executor(self, memory: ConversationBufferWindowMemory):
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            memory=memory,
            max_execution_time=Config.agent_max_execution_time,
        )
        return agent_executor
