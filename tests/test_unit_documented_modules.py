from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry
from agentic_sdk.memory import MemoryStore
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
from agentic_sdk.workflow import WorkflowState
from agentic_sdk.workflow.attachments import Attachment

from support import FoundryOpenAILikeClient, StaticVisionQueryBuilder


class DocumentedModuleUnitTests(unittest.TestCase):
    def test_pass_through_perceive_emits_query_payload(self) -> None:
        state = WorkflowState(user_message="  請介紹 TSiP  ")

        output = PassThroughPerceive()(state)

        self.assertEqual("retrieve", output["next_module"])
        self.assertEqual("請介紹 TSiP", output["payload"]["query"])

    def test_text_perceive_family_returns_plan_and_metadata(self) -> None:
        for module_cls in (TextPerceive, StructuredPerceive, TextImagePerceive):
            with self.subTest(module=module_cls.__name__):
                state = WorkflowState(user_message="幫我找支撐型鞋款")
                module = module_cls(client=FoundryOpenAILikeClient())

                output = module(state)

                self.assertEqual("plan", output["next_module"])
                self.assertEqual("test_intent", output["payload"]["perceived_intent"])
                self.assertEqual(ContextEntryType.PERCEIVED, output["context_updates"][0].type)

    def test_next_step_plan_uses_openai_decision(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.append(
            ContextEntry(
                type=ContextEntryType.PERCEIVED,
                content="intent=ask_tsip",
                metadata={"intent": "ask_tsip"},
            )
        )

        output = NextStepPlan(client=FoundryOpenAILikeClient(plan_sequence=["action"]))(state)

        self.assertEqual("action", output["next_module"])
        self.assertEqual("route to action", output["payload"]["plan_thought"])

    def test_keyword_retrieve_hits_expected_items(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.payload["query"] = "tsip"
        module = KeywordRetrieve(items=[{"keywords": ["tsip"], "content": "TSiP 介紹"}])

        output = module(state)

        self.assertEqual("action", output["next_module"])
        self.assertEqual("TSiP 介紹", output["payload"]["retrieved_snippet"])

    def test_semantic_retrieve_hits_knowledge_base(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(
            name="faq",
            entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")],
        )

        output = SemanticRetrieve(knowledge_base=kb)(state)

        self.assertEqual("plan", output["next_module"])
        self.assertIn("TSiP 是 AI 晶片藍圖", output["payload"]["retrieved_snippet"])

    def test_hybrid_retrieve_uses_vision_query_when_attachments_exist(self) -> None:
        state = WorkflowState(user_message="請看圖推薦")
        state.attachments = [
            Attachment(kind="image", mime="image/png", data_url="data:image/png;base64,AAAA", name="scan.png")
        ]
        kb = KnowledgeBase(
            name="faq",
            entries=[KnowledgeEntry(id="1", title="支撐鞋", content="支撐型慢跑鞋適合足弓支撐需求。")],
        )
        module = HybridRetrieve(
            knowledge_base=kb,
            vision_query=StaticVisionQueryBuilder("支撐鞋 足弓"),
        )

        output = module(state)

        self.assertIn("支撐型慢跑鞋", output["payload"]["retrieved_snippet"])
        self.assertTrue(output["context_updates"][0].metadata["vision_augmented"])

    def test_direct_answer_action_returns_latest_retrieved_content(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.append(
            ContextEntry(
                type=ContextEntryType.RETRIEVED,
                content="TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
                metadata={},
            )
        )

        output = DirectAnswerAction()(state)

        self.assertIsNone(output["next_module"])
        self.assertEqual(
            "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            state.last_action_result["content"],
        )

    def test_generative_action_family_returns_openai_client_content(self) -> None:
        for module_cls in (GenerativeAction, StructuredAction):
            with self.subTest(module=module_cls.__name__):
                state = WorkflowState(user_message="TSiP 是什麼？")
                state.payload["retrieved_snippet"] = "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"
                module = module_cls(
                    client=FoundryOpenAILikeClient(action_text="TSiP 是工研院主導的國產 AI 晶片落地藍圖。"),
                    model="foundry-openai-like",
                )

                output = module(state)

                self.assertIsNone(output["next_module"])
                self.assertEqual(
                    "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
                    state.last_action_result["content"],
                )

    def test_response_check_reflect_and_evidence_check_reflect_can_pass(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.last_action_result = {"content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"}

        response_output = ResponseCheckReflect(client=FoundryOpenAILikeClient())(state)
        evidence_output = EvidenceCheckReflect()(state)

        self.assertIsNone(response_output["next_module"])
        self.assertEqual("pass", response_output["payload"]["reflect_verdict"])
        self.assertIsNone(evidence_output["next_module"])
        self.assertEqual("pass", evidence_output["payload"]["reflect_verdict"])

    def test_text_perceive_writes_memory_when_memory_store_exists(self) -> None:
        temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        temp_file.close()
        try:
            store = MemoryStore(temp_file.name)
            state = WorkflowState(user_message="幫我找鞋")
            state.workflow_name = "test-workflow"
            state.memory_store = store

            TextPerceive(client=FoundryOpenAILikeClient())(state)

            entries = store.all_for_workflow("test-workflow")
            self.assertEqual(1, len(entries))
            self.assertEqual("user_input", entries[0].entry_type)
        finally:
            del store
            try:
                Path(temp_file.name).unlink(missing_ok=True)
            except PermissionError:
                pass


if __name__ == "__main__":
    unittest.main()