import os
import json
import subprocess
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

SYSTEM_PROMPT = """You are a highly capable voice-to-voice AI assistant and developer.
You have access to tools that allow you to read/write files, run terminal commands, spawn sub-agents, and restart yourself.
Because you are communicating via voice, keep your spoken responses concise and natural.
You can execute code and test it before returning a final verbal response. 
Use your tools generously to fulfill user requests!"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The absolute or relative path to the file."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write contents to a file. Overwrites if it exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The absolute or relative path to the file."},
                    "content": {"type": "string", "description": "The content to write to the file."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a terminal command in the project directory. Has a 30-second timeout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_agent",
            "description": "Terminate the current agent process and restart it. Use this after making changes to your own code.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_sub_agent",
            "description": "Spawn a sub-agent to handle a specific sub-task. It runs synchronously.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The description of the task for the sub-agent."}
                },
                "required": ["task"]
            }
        }
    }
]

def check_command_safety(command: str) -> bool:
    """Basic safety check for dangerous commands."""
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sda"]
    for d in dangerous:
        if d in command:
            return False
    return True

class Agent:
    def __init__(self, is_sub_agent=False, log_callback=None):
        self.log_callback = log_callback
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if is_sub_agent:
            self.messages[0]["content"] += "\nYou are a SUB-AGENT spawned to complete a specific task."

    async def _log(self, message):
        if self.log_callback:
            await self.log_callback(message)
        else:
            print(message)

    async def _execute_tool(self, tool_call):
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        await self._log(f"Agent executing tool: {name}({args})")
        
        try:
            if name == "read_file":
                with open(args["path"], "r") as f:
                    return f.read()
            elif name == "write_file":
                with open(args["path"], "w") as f:
                    f.write(args["content"])
                return f"Successfully wrote to {args['path']}"
            elif name == "run_command":
                command = args["command"]
                if not check_command_safety(command):
                    return "Error: Command rejected due to safety constraints."
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd="/mnt/shared/mallow/mallow-h",
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                output = f"Exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                return output
            elif name == "restart_agent":
                await self._log("Agent requested restart.")
                # Exit with code 42 to trigger restart in start.sh
                import sys
                sys.exit(42)
            elif name == "spawn_sub_agent":
                sub_agent = Agent(is_sub_agent=True, log_callback=self.log_callback)
                response = await sub_agent.chat(args["task"])
                return f"Sub-agent completed task with response: {response}"
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool execution failed: {str(e)}"

    async def chat_stream(self, user_message: str):
        import re
        self.messages.append({"role": "user", "content": user_message})
        
        while True:
            response = await client.chat.completions.create(
                model="deepseek/deepseek-chat",
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True
            )
            
            is_tool_call = False
            tool_calls_buffer = {}
            current_sentence = ""
            full_content = ""
            
            async for chunk in response:
                delta = chunk.choices[0].delta
                
                if delta.tool_calls:
                    is_tool_call = True
                    for tc in delta.tool_calls:
                        if tc.index not in tool_calls_buffer:
                            tool_calls_buffer[tc.index] = {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name or "", "arguments": ""}
                            }
                        if tc.function.name:
                            tool_calls_buffer[tc.index]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[tc.index]["function"]["arguments"] += tc.function.arguments
                    continue
                
                if not is_tool_call and delta.content:
                    full_content += delta.content
                    current_sentence += delta.content
                    
                    # Split by common sentence terminators
                    parts = re.split(r'([.!?:;\n]+)', current_sentence)
                    if len(parts) > 2:
                        # Reconstruct the completed sentences
                        # parts is like ["Hello", "!", " How are you", "?", ""]
                        complete_sentences = ""
                        for i in range(0, len(parts) - 1, 2):
                            complete_sentences += parts[i] + parts[i+1]
                        
                        remainder = parts[-1]
                        
                        clean_sentence = complete_sentences.strip()
                        if clean_sentence:
                            yield clean_sentence
                            
                        current_sentence = remainder
            
            if is_tool_call:
                tool_calls_list = []
                for idx, tc_data in tool_calls_buffer.items():
                    tool_calls_list.append({
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {
                            "name": tc_data["function"]["name"],
                            "arguments": tc_data["function"]["arguments"]
                        }
                    })
                
                self.messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls_list
                })
                
                for tc in tool_calls_list:
                    class FakeFunc:
                        name = tc["function"]["name"]
                        arguments = tc["function"]["arguments"]
                    class FakeTC:
                        id = tc["id"]
                        function = FakeFunc()
                    
                    tool_result = await self._execute_tool(FakeTC())
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "content": str(tool_result)
                    })
                
                # Continue loop to send tool results to LLM
                continue
            else:
                if current_sentence.strip():
                    yield current_sentence.strip()
                
                self.messages.append({"role": "assistant", "content": full_content})
                break

