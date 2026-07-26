import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO_ROOT)
sys.path.insert(0, REPO_ROOT)

from agentic_sdk import Workflow
from agentic_sdk.modules import KeywordRetrieve, PassThroughPerceive, ToolCallAction


tool_model = os.environ.get("AGENTIC_TOOL_MODEL", os.environ.get("AGENTIC_OLLAMA_MODEL", "llama3.2:1b"))
tool_base_url = os.environ.get("AGENTIC_TOOL_BASE_URL", "http://localhost:11434/v1/")
tool_api_key = os.environ.get("AGENTIC_TOOL_API_KEY", "ollama")

tools = [
    {
        "type": "function",
        "function": {
            "name": "submit_booking",
            "description": "提交球場預約資料。",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "預約人姓名。",
                    },
                    "booking_time": {
                        "type": "string",
                        "description": "使用者想預約的日期與時間。",
                    },
                },
                "required": ["customer_name", "booking_time"],
                "additionalProperties": False,
            },
        },
    }
]

workflow = Workflow(
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(
        items=[
            {
                "keywords": ["booking", "預約", "球場"],
                "content": "球場預約需要留下姓名與預約時間。",
            },
        ],
    ),
    action=ToolCallAction(
        api_key=tool_api_key,
        base_url=tool_base_url,
        model=tool_model,
        temperature=0.2,
        system_prompt="使用者要預約球場時，請呼叫 submit_booking tool 取得預約人姓名與預約時間。",
        tools=tools,
    ),
)

result = workflow.run("我想預約明天下午三點的球場，姓名是王小明。")
print(result.final_message)
print(json.dumps(result.entities.get("latest_tool_calls", []), ensure_ascii=False, indent=2))