from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_sdk import Workflow
from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry
from agentic_sdk.modules import (
    DirectAnswerAction,
    EvidenceCheckReflect,
    GenerativeAction,
    HybridRetrieve,
    KeywordRetrieve,
    NextStepPlan,
    PassThroughPerceive,
    ResponseCheckReflect,
    SemanticRetrieve,
    StructuredAction,
    StructuredPerceive,
    TextImagePerceive,
    TextPerceive,
)
from agentic_sdk.workflow.attachments import Attachment

from support import ActionToReflectWrapper, FoundryOpenAILikeClient, StaticVisionQueryBuilder


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


def _llm_params() -> dict[str, str]:
    return {"api_key": TEST_API_KEY, "base_url": TEST_BASE_URL, "model": TEST_MODEL}


class DocumentedWorkflowIntegrationTests(unittest.TestCase):
    def test_minimal_readme_modules_run_in_workflow(self) -> None:
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            retrieve=KeywordRetrieve(
                items=[{"keywords": ["tsip"], "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"}]
            ),
            action=DirectAnswerAction(),
        )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)
        self.assertEqual({"perceive": 1, "retrieve": 1, "action": 1}, result.visit_counts)

    def test_text_perceive_semantic_retrieve_generative_reflect_workflow_runs(self) -> None:
        kb = KnowledgeBase(
            name="faq",
            entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是工研院主導的國產 AI 晶片落地藍圖。")],
        )
        client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "action"], reflect_verdict="pass")
        action_client = FoundryOpenAILikeClient(action_text="TSiP 是工研院主導的國產 AI 晶片落地藍圖。")
        with patch("agentic_sdk.workflow.llm.OpenAI", side_effect=[client, client, action_client, client]):
            workflow = Workflow(
                perceive=TextPerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=SemanticRetrieve(knowledge_base=kb),
                action=ActionToReflectWrapper(
                    GenerativeAction(**_llm_params())
                ),
                reflect=ResponseCheckReflect(**_llm_params()),
            )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)
        self.assertEqual(1, result.visit_counts["perceive"])
        self.assertEqual(2, result.visit_counts["plan"])
        self.assertEqual(1, result.visit_counts["retrieve"])
        self.assertEqual(1, result.visit_counts["action"])
        self.assertEqual(1, result.visit_counts["reflect"])

    def test_structured_perceive_hybrid_retrieve_structured_action_workflow_runs(self) -> None:
        kb = KnowledgeBase(
            name="faq",
            entries=[KnowledgeEntry(id="1", title="支撐鞋", content="建議優先考慮支撐型慢跑鞋。")],
        )
        client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "action"])
        action_client = FoundryOpenAILikeClient(action_text="建議優先考慮支撐型慢跑鞋。")
        with patch("agentic_sdk.workflow.llm.OpenAI", side_effect=[client, client, action_client]):
            workflow = Workflow(
                perceive=StructuredPerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=HybridRetrieve(knowledge_base=kb),
                action=ActionToReflectWrapper(
                    StructuredAction(**_llm_params())
                ),
                reflect=EvidenceCheckReflect(),
            )

        result = workflow.run("我最近久站後足弓很酸，想找比較有支撐的鞋")

        self.assertEqual("建議優先考慮支撐型慢跑鞋。", result.final_message)
        self.assertEqual(1, result.visit_counts["reflect"])

    def test_text_image_perceive_with_vision_query_builder_runs(self) -> None:
        kb = KnowledgeBase(
            name="faq",
            entries=[KnowledgeEntry(id="1", title="足測推薦", content="支撐型慢跑鞋適合足弓支撐需求。")],
        )
        client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "action"])
        action_client = FoundryOpenAILikeClient(action_text="支撐型慢跑鞋適合足弓支撐需求。")
        with patch("agentic_sdk.workflow.llm.OpenAI", side_effect=[client, client, action_client]):
            workflow = Workflow(
                perceive=TextImagePerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=SemanticRetrieve(
                    knowledge_base=kb,
                    vision_query=StaticVisionQueryBuilder("足測推薦 足弓 支撐鞋"),
                ),
                action=ActionToReflectWrapper(
                    GenerativeAction(**_llm_params())
                ),
                reflect=EvidenceCheckReflect(),
            )

        result = workflow.run(
            "請根據這張足測圖推薦鞋款",
            attachments=[
                Attachment(kind="image", mime="image/png", data_url="data:image/png;base64,AAAA", name="foot.png")
            ],
        )

        self.assertEqual("支撐型慢跑鞋適合足弓支撐需求。", result.final_message)
        retrieved_entries = [entry for entry in result.entries if entry.type == "retrieved"]
        self.assertTrue(retrieved_entries)
        self.assertIn("支撐型慢跑鞋", retrieved_entries[-1].content)


if __name__ == "__main__":
    unittest.main()