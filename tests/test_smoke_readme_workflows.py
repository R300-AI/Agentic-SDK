from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, GenerativeAction, KeywordRetrieve, PassThroughPerceive, ToolCallAction

from support import FoundryOpenAILikeClient


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


class ReadmeWorkflowSmokeTests(unittest.TestCase):
    def test_readme_example_one_path(self) -> None:
        workflow = Workflow(
            workflow_name="知識問答 Agent",
            description="根據內建關鍵字知識庫回答常見問題。",
            perceive=PassThroughPerceive(),
            retrieve=KeywordRetrieve(
                items=[
                    {"keywords": ["agentic sdk", "sdk"], "content": "Agentic SDK 是一個以 workflow 組裝 agent 行為的 Python library。"},
                    {"keywords": ["tsip"], "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"},
                ]
            ),
            action=DirectAnswerAction(),
        )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)

    def test_readme_example_two_path(self) -> None:
        openai_client = FoundryOpenAILikeClient(action_text="TSiP 是工研院主導的國產 AI 晶片落地藍圖。")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=openai_client):
            workflow = Workflow(
                workflow_name="Foundry 回覆 Agent",
                description="用 OpenAI-compatible 模型整理檢索結果並生成自然語句回覆。",
                perceive=PassThroughPerceive(),
                retrieve=KeywordRetrieve(
                    items=[
                        {"keywords": ["tsip"], "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"}
                    ]
                ),
                action=GenerativeAction(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, model=TEST_MODEL),
            )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)

    def test_readme_example_three_path(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_booking",
                    "description": "提交球場預約資料。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_name": {"type": "string", "description": "預約人姓名。"},
                            "booking_time": {"type": "string", "description": "使用者想預約的日期與時間。"},
                        },
                        "required": ["customer_name", "booking_time"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        tool_calls = [
            {
                "id": "call_booking",
                "type": "function",
                "function": {"name": "submit_booking", "arguments": '{"customer_name":"王小明","booking_time":"明天下午三點"}'},
            }
        ]
        openai_client = FoundryOpenAILikeClient(action_text="已準備提交預約資料。", tool_calls=tool_calls)
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=openai_client):
            workflow = Workflow(
                workflow_name="預約工具 Agent",
                description="根據使用者輸入判斷是否要發出預約工具呼叫。",
                perceive=PassThroughPerceive(),
                retrieve=KeywordRetrieve(
                    items=[
                        {"keywords": ["booking", "預約", "球場"], "content": "球場預約需要留下姓名與預約時間。"}
                    ]
                ),
                action=ToolCallAction(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, model=TEST_MODEL, tools=tools),
            )

        result = workflow.run("我想預約明天下午三點的球場，姓名是王小明。")

        self.assertEqual("已準備提交預約資料。", result.final_message)
        self.assertEqual(tools, openai_client.last_create_kwargs["tools"])
        self.assertEqual(tool_calls, result.entities["latest_tool_calls"])

    def test_readme_example_four_path(self) -> None:
        class SummaryAction:
            def __call__(self, state):
                summary = state.lookup("latest_retrieved_content") or "沒有命中任何條目。"
                return f"自訂 Action 回傳：{summary}"

        workflow = Workflow(
            workflow_name="摘要處理 Agent",
            description="把檢索內容交給自訂 Action 做二次整理。",
            perceive=PassThroughPerceive(),
            retrieve=KeywordRetrieve(
                items=[
                    {"keywords": ["agentic sdk", "sdk"], "content": "Agentic SDK 讓你用 workflow 組裝 agent 行為。"}
                ]
            ),
            action=SummaryAction(),
        )

        result = workflow.run("請介紹 Agentic SDK")

        self.assertEqual("自訂 Action 回傳：Agentic SDK 讓你用 workflow 組裝 agent 行為。", result.final_message)


if __name__ == "__main__":
    unittest.main()