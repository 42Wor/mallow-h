import os
import json
import subprocess
from openai import AsyncOpenAI
from dotenv import load_dotenv
import re

load_dotenv()

DEFAULT_IGNORE_DIRS = {
    "venv", ".venv", "env", "node_modules", 
    "__pycache__", ".git", ".idea", ".vscode"
}
DEFAULT_IGNORE_FILES = {".env", ".DS_Store", "pyc"}

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

SYSTEM_PROMPT = """
You are an expert AI software agent equipped with workspace manipulation tools.

### Speech-to-Text (STT) Normalization Rules:
1. Speech recognition may mishear code terms and filenames:
   - "agent dot p y", "agent pie", "agent p y" -> `agent.py`
   - "app dot p y", "app pie" -> `app.py`
   - "requirements dot t x t" -> `requirements.txt`
   - "start dot s h" -> `start.sh`
2. If a user asks to read, edit, or inspect a file and the filename sounds misspelled or unclear, DO NOT guess or fail. Use `list_directory_tree` or `fuzzy_find_file` first to locate the exact path in the workspace.

### Workspace Safety & Ignore Rules:
1. NEVER search or inspect binary files, virtual environments (`venv/`, `.venv/`, `env/`), `node_modules/`, `__pycache__/`, `.git/`, or sensitive environment credential files (`.env`).
2. Always respect default ignore patterns unless explicitly instructed otherwise by the user.
3. Keep file search results concise and relevant.
"""

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
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory_tree",
            "description": "Lists the directory tree structure and paths in the workspace, ignoring virtual environments and env files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": ".", "description": "Directory path to map."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Searches for a specific word, function, or text inside project files while automatically ignoring venv and .env files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Word or phrase to search for inside files."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fuzzy_find_file",
            "description": "Locates a file when the spoken filename is uncertain or misheard by STT (e.g. 'agent p y').",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename_query": {"type": "string", "description": "Target filename or partial spoken name."}
                },
                "required": ["filename_query"]
            }
        }
    }
]

def list_directory_tree(path=".", max_depth=3, current_depth=0):
    if current_depth > max_depth:
        return ""
    
    tree_str = ""
    try:
        items = sorted(os.listdir(path))
    except Exception as e:
        return f"Error reading directory {path}: {str(e)}\n"

    for item in items:
        if item in DEFAULT_IGNORE_DIRS or item in DEFAULT_IGNORE_FILES or item.endswith(".pyc"):
            continue
        
        full_path = os.path.join(path, item)
        indent = "  " * current_depth
        
        if os.path.isdir(full_path):
            tree_str += f"{indent}📁 {item}/\n"
            tree_str += list_directory_tree(full_path, max_depth, current_depth + 1)
        else:
            tree_str += f"{indent}📄 {item}\n"
            
    return tree_str


def search_codebase(query, directory=".", max_results=20):
    matches = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]

        for file in files:
            if file in DEFAULT_IGNORE_FILES or file.endswith((".pyc", ".png", ".jpg", ".tar", ".gz")):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern.search(line):
                            matches.append(f"{file_path}:{line_num}: {line.strip()}")
                            if len(matches) >= max_results:
                                return "\n".join(matches) + f"\n\n(Truncated to top {max_results} matches)"
            except Exception:
                continue

    return "\n".join(matches) if matches else f"No occurrences of '{query}' found."


def fuzzy_find_file(filename_query, directory="."):
    clean_query = filename_query.lower().replace(" dot ", ".").replace(" ", "")
    found_files = []

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]

        for file in files:
            if file in DEFAULT_IGNORE_FILES:
                continue
            
            clean_file = file.lower()
            if clean_query in clean_file or clean_file in clean_query:
                found_files.append(os.path.join(root, file))

    if not found_files:
        return f"No files matching '{filename_query}' found."
    return "Matching files found:\n" + "\n".join(f"- {f}" for f in found_files)


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
            if name == "list_directory_tree":
                return list_directory_tree(path=args.get("path", "."))
            elif name == "search_codebase":
                return search_codebase(query=args.get("query"))
            elif name == "fuzzy_find_file":
                return fuzzy_find_file(filename_query=args.get("filename_query"))
            elif name == "read_file":
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
                    
                    # Split by punctuation followed by whitespace, or newlines
                    parts = re.split(r'([.!?:;]+\s+|\n+)', current_sentence)
                    if len(parts) > 2:
                        # Reconstruct the completed sentences
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

