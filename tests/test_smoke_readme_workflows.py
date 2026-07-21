from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, GenerativeAction, KeywordRetrieve, PassThroughPerceive

from support import FoundryOpenAILikeClient


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


class ReadmeWorkflowSmokeTests(unittest.TestCase):
    def test_readme_example_one_path(self) -> None:
        workflow = Workflow(
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
        class SummaryAction:
            def __call__(self, memory):
                summary = memory.lookup("latest_retrieved_content") or "沒有命中任何條目。"
                return f"自訂 Action 回傳：{summary}"

        workflow = Workflow(
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