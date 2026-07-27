from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from agentic_sdk import InMemoryConversationStore, InMemoryStore, Workflow
from agentic_sdk.core import Attachment
from agentic_sdk.modules import (
    DirectAnswerAction,
    EvidenceCheckReflect,
    GenerativeAction,
    HybridRetrieve,
    KeywordRetrieve,
    NextStepPlan,
    PassThroughPerceive,
    PassThroughRetrieve,
    ResponseCheckReflect,
    SemanticRetrieve,
    TextImagePerceive,
    TextPerceive,
)

from support import ActionToReflectWrapper, FoundryOpenAILikeClient, StaticVisionQueryBuilder


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


def _llm_params() -> dict[str, str]:
    return {"api_key": TEST_API_KEY, "base_url": TEST_BASE_URL, "model": TEST_MODEL}


@dataclass
class KnowledgeEntry:
    id: str
    title: str
    content: str


@dataclass
class KnowledgeHit:
    entry: KnowledgeEntry

    def __str__(self) -> str:
        return f"[{self.entry.title}] {self.entry.content}"


class KnowledgeBase:
    def __init__(self, entries: list[KnowledgeEntry]) -> None:
        self._entries = entries

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        normalized = query.lower()
        hits = [
            KnowledgeHit(entry)
            for entry in self._entries
            if entry.title.lower() in normalized or any(token and token in entry.content.lower() for token in normalized.split())
        ]
        return hits[:top_k]


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

    def test_plan_and_reflect_slots_are_reachable_without_action_wrapper(self) -> None:
        plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve"])
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=plan_client):
            workflow = Workflow(
                perceive=PassThroughPerceive(),
                plan=NextStepPlan(**_llm_params()),
                retrieve=KeywordRetrieve(
                    items=[{"keywords": ["tsip"], "content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"}]
                ),
                action=DirectAnswerAction(),
                reflect=EvidenceCheckReflect(),
            )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)
        self.assertEqual({"perceive": 1, "plan": 1, "retrieve": 1, "action": 1, "reflect": 1}, result.visit_counts)

    def test_text_perceive_semantic_retrieve_generative_reflect_workflow_runs(self) -> None:
        kb = KnowledgeBase(
            entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是工研院主導的國產 AI 晶片落地藍圖。")]
        )
        perceive_client = FoundryOpenAILikeClient()
        plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve"])
        action_client = FoundryOpenAILikeClient(action_text="TSiP 是工研院主導的國產 AI 晶片落地藍圖。")
        reflect_client = FoundryOpenAILikeClient(reflect_verdict="pass")
        with patch(
            "agentic_sdk.llm.openai_compatible.OpenAI",
            side_effect=[perceive_client, plan_client, action_client, reflect_client],
        ):
            workflow = Workflow(
                perceive=TextPerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=SemanticRetrieve(knowledge_base=kb),
                action=ActionToReflectWrapper(GenerativeAction(**_llm_params())),
                reflect=ResponseCheckReflect(**_llm_params()),
            )

        result = workflow.run("TSiP 是什麼？")

        self.assertEqual("TSiP 是工研院主導的國產 AI 晶片落地藍圖。", result.final_message)
        self.assertEqual(1, result.visit_counts["perceive"])
        self.assertEqual(1, result.visit_counts["plan"])
        self.assertEqual(1, result.visit_counts["retrieve"])
        self.assertEqual(1, result.visit_counts["action"])
        self.assertEqual(1, result.visit_counts["reflect"])

    def test_text_perceive_hybrid_retrieve_generative_action_workflow_runs(self) -> None:
        kb = KnowledgeBase(
            entries=[KnowledgeEntry(id="1", title="支撐鞋", content="建議優先考慮支撐型慢跑鞋。")]
        )
        perceive_client = FoundryOpenAILikeClient()
        plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve"])
        action_client = FoundryOpenAILikeClient(action_text="建議優先考慮支撐型慢跑鞋。")
        with patch(
            "agentic_sdk.llm.openai_compatible.OpenAI",
            side_effect=[perceive_client, plan_client, action_client],
        ):
            workflow = Workflow(
                perceive=TextPerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=HybridRetrieve(knowledge_base=kb),
                action=ActionToReflectWrapper(GenerativeAction(**_llm_params())),
                reflect=EvidenceCheckReflect(),
            )

        result = workflow.run("我最近久站後足弓很酸，想找比較有支撐的鞋")

        self.assertEqual("建議優先考慮支撐型慢跑鞋。", result.final_message)
        self.assertEqual(1, result.visit_counts["reflect"])

    def test_text_image_perceive_with_vision_query_builder_runs(self) -> None:
        kb = KnowledgeBase(
            entries=[KnowledgeEntry(id="1", title="足測推薦", content="支撐型慢跑鞋適合足弓支撐需求。")]
        )
        perceive_client = FoundryOpenAILikeClient()
        plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve"])
        action_client = FoundryOpenAILikeClient(action_text="支撐型慢跑鞋適合足弓支撐需求。")
        with patch(
            "agentic_sdk.llm.openai_compatible.OpenAI",
            side_effect=[perceive_client, plan_client, action_client],
        ):
            workflow = Workflow(
                perceive=TextImagePerceive(**_llm_params()),
                plan=NextStepPlan(**_llm_params()),
                retrieve=SemanticRetrieve(
                    knowledge_base=kb,
                    vision_query=StaticVisionQueryBuilder("足測推薦 足弓 支撐鞋"),
                ),
                action=ActionToReflectWrapper(GenerativeAction(**_llm_params())),
                reflect=EvidenceCheckReflect(),
            )

        result = workflow.run(
            "請根據這張足測圖推薦鞋款",
            attachments=[Attachment(kind="image", content="data:image/png;base64,AAAA", media_type="image/png", name="foot.png")],
        )

        self.assertEqual("支撐型慢跑鞋適合足弓支撐需求。", result.final_message)
        retrieved_entries = [entry for entry in result.entries if entry.type == "retrieved"]
        self.assertTrue(retrieved_entries)
        self.assertIn("支撐型慢跑鞋", retrieved_entries[-1].content)

    def test_workflow_run_persists_full_conversation_history_by_session(self) -> None:
        conversation_store = InMemoryConversationStore()
        first_client = FoundryOpenAILikeClient(action_text="第一輪回答")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=first_client):
            first_workflow = Workflow(
                perceive=PassThroughPerceive(),
                retrieve=PassThroughRetrieve(),
                action=GenerativeAction(**_llm_params()),
                conversation_store=conversation_store,
            )

        first_result = first_workflow.run("第一輪問題", session_id="session-42")

        self.assertEqual("第一輪回答", first_result.final_message)
        self.assertIsNotNone(first_result.memory)
        self.assertEqual(["user", "assistant"], [turn.role for turn in first_result.memory.turns])
        self.assertIsNotNone(first_result.in_context_memory)

        second_client = FoundryOpenAILikeClient(action_text="第二輪回答")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=second_client):
            second_workflow = Workflow(
                perceive=PassThroughPerceive(),
                retrieve=PassThroughRetrieve(),
                action=GenerativeAction(**_llm_params()),
                conversation_store=conversation_store,
            )

        second_result = second_workflow.run("第二輪追問", session_id="session-42")

        self.assertEqual("第二輪回答", second_result.final_message)
        self.assertEqual(
            ["user", "assistant", "user", "assistant"],
            [turn.role for turn in second_result.memory.turns],
        )
        self.assertEqual(
            ["system", "user", "assistant", "user"],
            [message["role"] for message in second_client.last_create_kwargs["messages"]],
        )
        self.assertEqual("第一輪問題", second_client.last_create_kwargs["messages"][1]["content"])
        self.assertEqual("第一輪回答", second_client.last_create_kwargs["messages"][2]["content"])
        self.assertEqual("第二輪追問", second_client.last_create_kwargs["messages"][3]["content"])

    def test_workflow_run_accepts_primary_persistent_memory(self) -> None:
        client = FoundryOpenAILikeClient(action_text="第二輪回答")
        primary_memory = InMemoryStore(workflow_name="default", workflow_id="wf-0", session_id="session-77")
        primary_memory.append_message("user", "第一輪問題")
        primary_memory.append_message("assistant", "第一輪回答")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            workflow = Workflow(
                perceive=PassThroughPerceive(),
                retrieve=PassThroughRetrieve(),
                action=GenerativeAction(**_llm_params()),
            )

        result = workflow.run("第二輪追問", session_id="session-77", memory=primary_memory)

        self.assertEqual("第二輪回答", result.final_message)
        self.assertIsNotNone(result.memory)
        self.assertEqual(["user", "assistant", "user", "assistant"], [turn.role for turn in result.memory.turns])
        self.assertEqual(["system", "user", "assistant", "user"], [message["role"] for message in client.last_create_kwargs["messages"]])


if __name__ == "__main__":
    unittest.main()