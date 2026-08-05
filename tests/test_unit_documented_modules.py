from __future__ import annotations

import importlib.util
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, WorkflowState
from agentic_sdk.memory import InContextMemory, InMemoryStore
from agentic_sdk.modules import (
    DirectAnswerAction,
    EvidenceCheckReflect,
    GenerativeAction,
    KeywordRetrieve,
    NextStepPlan,
    PassThroughPerceive,
    ResponseCheckReflect,
    SemanticRetrieve,
    TextImagePerceive,
    TextPerceive,
    ToolCallAction,
)

from support import FoundryOpenAILikeClient, StaticVisionQueryBuilder


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


def _llm_params(model: str = TEST_MODEL) -> dict[str, str]:
    return {"api_key": TEST_API_KEY, "base_url": TEST_BASE_URL, "model": model}


@dataclass
class KnowledgeEntry:
    id: str
    title: str
    content: str


@dataclass
class KnowledgeHit:
    entry: KnowledgeEntry
    score: float = 1.0

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


class StaticEmbedder:
    def embed(self, text: str) -> list[float]:
        return [float(len(text) or 1), 1.0]


class DocumentedModuleUnitTests(unittest.TestCase):
    def test_image_category_examples_require_an_explicit_selected_result(self) -> None:
        from agentic_sdk.modules.action.generative import _build_messages
        from agentic_sdk.modules.perceive.text import _SYSTEM_PROMPT

        state = WorkflowState(user_message="請分析圖片")
        state.payload["perceived_details"] = {"image": "foot chart"}
        messages = _build_messages(state, "test system prompt")
        extra_context = next(message["content"] for message in messages if message["role"] == "system")

        self.assertIn("selected result or result field", _SYSTEM_PROMPT)
        self.assertIn("左右腳", extra_context)
        self.assertIn("選取結果或結果欄位", extra_context)

    def test_faiss_knowledge_base_chunks_long_documents(self) -> None:
        from agentic_sdk.modules.retrieve.semantic import FaissKnowledgeBase

        long_text = "\n\n".join(f"段落{i}：" + ("內容" * 220) for i in range(4))
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "knowledge"
            source_dir.mkdir()
            document_path = source_dir / "guide.md"
            document_path.write_text(long_text, encoding="utf-8")
            knowledge_base = FaissKnowledgeBase(
                index_path=str(Path(temp_dir) / "artifacts"),
                source_path=str(source_dir),
                embedder=StaticEmbedder(),
            )

            documents = knowledge_base._load_documents()

        self.assertGreater(len(documents), 1)
        self.assertEqual({str(document_path)}, {entry["path"] for entry in documents})
        self.assertEqual(list(range(len(documents))), [entry["chunk_index"] for entry in documents])
        self.assertTrue(all(entry["chunk_count"] == len(documents) for entry in documents))
        self.assertTrue(all(len(entry["content"]) <= FaissKnowledgeBase._DEFAULT_CHUNK_SIZE for entry in documents))

    def test_faiss_knowledge_base_uses_saved_source_copy(self) -> None:
        from agentic_sdk.modules.retrieve.semantic import FaissKnowledgeBase

        with tempfile.TemporaryDirectory() as temp_dir:
            original_dir = Path(temp_dir) / "external"
            saved_dir = Path(temp_dir) / "saved"
            original_dir.mkdir()
            original_path = original_dir / "policy.md"
            original_path.write_text("Policy text", encoding="utf-8")

            knowledge_base = FaissKnowledgeBase(
                index_path=str(saved_dir / "vectorstore"),
                source_paths=[str(original_path)],
                saved_source_path=str(saved_dir / "source-files"),
                embedder=StaticEmbedder(),
            )

            documents = knowledge_base._load_documents()
            copied_path = saved_dir / "source-files" / "policy.md"
            self.assertTrue(copied_path.exists())
            self.assertEqual({str(copied_path)}, {entry["path"] for entry in documents})

    def test_semantic_retrieve_facade_forwards_chunk_config(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")])

        with patch("agentic_sdk.modules.retrieve.semantic.OpenAIEmbedder") as embedder_cls, patch(
            "agentic_sdk.modules.retrieve.semantic.FaissKnowledgeBase"
        ) as kb_cls:
            embedder = object()
            embedder_cls.return_value = embedder
            kb_cls.return_value = kb

            SemanticRetrieve(
                provider="openai",
                api_key=TEST_API_KEY,
                base_url=TEST_BASE_URL,
                embedding_model="text-embedding-3-small",
                sources=["./knowledge/guide.md"],
                saved_path="./artifacts/kb",
                chunk_size=800,
                chunk_overlap=120,
            )(state)

        _, kwargs = kb_cls.call_args
        self.assertEqual("artifacts/kb/vectorstore", kwargs["index_path"].replace("\\", "/").lstrip("./"))
        self.assertEqual(["./knowledge/guide.md"], kwargs["source_paths"])
        self.assertEqual("artifacts/kb/source-files", kwargs["saved_source_path"].replace("\\", "/").lstrip("./"))
        self.assertIs(True, kwargs["rebuild_if_missing"])
        self.assertIs(True, kwargs["rebuild_if_stale"])
        self.assertEqual(800, kwargs["chunk_size"])
        self.assertEqual(120, kwargs["chunk_overlap"])

    def test_semantic_retrieve_facade_builds_default_components(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")])

        with patch("agentic_sdk.modules.retrieve.semantic.OpenAIEmbedder") as embedder_cls, patch(
            "agentic_sdk.modules.retrieve.semantic.FaissKnowledgeBase"
        ) as kb_cls:
            embedder = object()
            embedder_cls.return_value = embedder
            kb_cls.return_value = kb

            output = SemanticRetrieve(
                provider="openai",
                api_key=TEST_API_KEY,
                base_url=TEST_BASE_URL,
                embedding_model="text-embedding-3-small",
                sources=["./knowledge"],
                saved_path="./artifacts/kb",
            )(state)

        embedder_cls.assert_called_once()
        kb_cls.assert_called_once()
        _, kwargs = kb_cls.call_args
        self.assertEqual("artifacts/kb/vectorstore", kwargs["index_path"].replace("\\", "/").lstrip("./"))
        self.assertEqual(["./knowledge"], kwargs["source_paths"])
        self.assertEqual("artifacts/kb/source-files", kwargs["saved_source_path"].replace("\\", "/").lstrip("./"))
        self.assertIs(True, kwargs["rebuild_if_missing"])
        self.assertIs(True, kwargs["rebuild_if_stale"])
        self.assertIn("TSiP 是 AI 晶片藍圖", output["payload"]["retrieved_snippet"])

    def test_semantic_retrieve_override_components_take_precedence(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")])

        with patch("agentic_sdk.modules.retrieve.semantic.OpenAIEmbedder") as embedder_cls, patch(
            "agentic_sdk.modules.retrieve.semantic.FaissKnowledgeBase"
        ) as kb_cls:
            output = SemanticRetrieve(
                provider="openai",
                api_key=TEST_API_KEY,
                base_url=TEST_BASE_URL,
                embedding_model="text-embedding-3-small",
                sources=["./knowledge"],
                saved_path="./artifacts/kb",
                embedder=object(),
                knowledge_base=kb,
            )(state)

        embedder_cls.assert_not_called()
        kb_cls.assert_not_called()
        self.assertIn("TSiP 是 AI 晶片藍圖", output["payload"]["retrieved_snippet"])

    def test_pass_through_perceive_emits_query_payload(self) -> None:
        state = WorkflowState(user_message="  請介紹 TSiP  ")

        output = PassThroughPerceive()(state)

        self.assertEqual("retrieve", output["next_module"])
        self.assertEqual("請介紹 TSiP", output["payload"]["query"])

    def test_text_perceive_family_returns_plan_and_metadata(self) -> None:
        for module_cls in (TextPerceive, TextImagePerceive):
            with self.subTest(module=module_cls.__name__):
                state = WorkflowState(user_message="幫我找支撐型鞋款")
                with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient()):
                    module = module_cls(**_llm_params())

                output = module(state)

                self.assertEqual("plan", output["next_module"])
                self.assertEqual("test_intent", output["payload"]["perceived_intent"])
                self.assertEqual(ContextEntryType.PERCEIVED, output["context_updates"][0].type)

    def test_text_perceive_sends_guidance_and_fields_to_openai(self) -> None:
        state = WorkflowState(user_message="客人說鞋底磨壞了，想知道能不能換。")
        client = FoundryOpenAILikeClient()
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = TextPerceive(
                welcome_message="先看出客人想問什麼。",
                options=[{"label": "客人需求", "intent": "客人想解決的問題或想買的東西"}],
                **_llm_params(),
            )

        module(state)

        messages = client.last_create_kwargs["messages"]
        user_content = messages[1]["content"]
        self.assertIsInstance(user_content, str)
        self.assertIn("guidance: 先看出客人想問什麼。", user_content)
        self.assertIn("fields_to_notice", user_content)
        self.assertIn("客人需求", user_content)

    def test_text_perceive_includes_full_conversation_history(self) -> None:
        conversation = InContextMemory(workflow_name="demo", workflow_id="wf-1", session_id="session-1")
        conversation.append_message("user", "第一輪問題")
        conversation.append_message("assistant", "第一輪回答")
        conversation.append_message("user", "第二輪追問")
        state = WorkflowState(user_message="第二輪追問", memory=conversation)
        client = FoundryOpenAILikeClient()
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = TextPerceive(**_llm_params())

        module(state)

        messages = client.last_create_kwargs["messages"]
        self.assertEqual(["system", "user", "assistant", "user"], [message["role"] for message in messages])
        self.assertEqual("第一輪問題", messages[1]["content"])
        self.assertEqual("第一輪回答", messages[2]["content"])
        self.assertEqual("第二輪追問", messages[3]["content"])

    def test_text_image_perceive_sends_image_instruction_and_image_to_openai(self) -> None:
        state = WorkflowState(user_message="請看照片判斷鞋底狀況。")
        state.attachments = [
            Attachment(kind="image", content="data:image/png;base64,AAAA", media_type="image/png", name="sole.png")
        ]
        client = FoundryOpenAILikeClient()
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = TextImagePerceive(
                welcome_message="先看出客人想問什麼。",
                options=[{"label": "破損位置", "intent": "照片中看得到的磨損或破損位置"}],
                image_instruction="看清楚破損位置與標籤文字，看不到就說看不清楚。",
                **_llm_params(),
            )

        module(state)

        messages = client.last_create_kwargs["messages"]
        user_content = messages[1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual("text", user_content[0]["type"])
        self.assertIn("image_instruction: 看清楚破損位置與標籤文字", user_content[0]["text"])
        self.assertIn("input_images", user_content[0]["text"])
        self.assertEqual("image_url", user_content[1]["type"])
        self.assertEqual("data:image/png;base64,AAAA", user_content[1]["image_url"]["url"])
        system_prompt = client.last_create_kwargs["messages"][0]["content"]
        self.assertIn("only report a value as a named fact", system_prompt)
        self.assertIn("Never treat an unmarked comparison chart", system_prompt)

    def test_next_step_plan_uses_openai_decision(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.append(
            ContextEntry(
                type=ContextEntryType.PERCEIVED,
                content="intent=ask_tsip",
                metadata={"intent": "ask_tsip"},
            )
        )

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient(plan_sequence=["action"])):
            output = NextStepPlan(**_llm_params())(state)

        self.assertEqual("action", output["next_module"])
        self.assertEqual("route to action", output["payload"]["plan_thought"])

    def test_next_step_plan_retrieves_catalog_facts_before_action(self) -> None:
        state = WorkflowState(user_message="請依 catalog 推薦產品編號 230619521，列出價格與限制。")
        state.append(
            ContextEntry(
                type=ContextEntryType.PERCEIVED,
                content="intent=product_recommendation",
                metadata={"intent": "product_recommendation"},
            )
        )

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient(plan_sequence=["action"])):
            output = NextStepPlan(retrieve_description="LaNew catalog", **_llm_params())(state)

        self.assertEqual("retrieve", output["next_module"])

    def test_next_step_plan_retrieves_retail_sku_and_availability_before_action(self) -> None:
        state = WorkflowState(user_message="SKU 7037191 有現貨、展示品或調貨資訊嗎？")
        state.append(
            ContextEntry(
                type=ContextEntryType.PERCEIVED,
                content="intent=store_availability",
                metadata={"intent": "store_availability"},
            )
        )

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient(plan_sequence=["action"])):
            output = NextStepPlan(retrieve_description="LaNew catalog", **_llm_params())(state)

        self.assertEqual("retrieve", output["next_module"])

    def test_keyword_retrieve_hits_expected_items(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.payload["query"] = "tsip"
        module = KeywordRetrieve(items=[{"keywords": ["tsip"], "content": "TSiP 介紹"}])

        output = module(state)

        self.assertEqual("action", output["next_module"])
        self.assertEqual("TSiP 介紹", output["payload"]["retrieved_snippet"])

    def test_semantic_retrieve_hits_knowledge_base(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")])

        output = SemanticRetrieve(knowledge_base=kb)(state)

        self.assertEqual("action", output["next_module"])
        self.assertIn("TSiP 是 AI 晶片藍圖", output["payload"]["retrieved_snippet"])

    def test_semantic_retrieve_formats_knowledge_hits_readably(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="TSiP", content="TSiP 是 AI 晶片藍圖。")])

        output = SemanticRetrieve(knowledge_base=kb)(state)

        snippet = output["payload"]["retrieved_snippet"]
        self.assertIn("Knowledge hits:", snippet)
        self.assertIn("1. TSiP", snippet)
        self.assertIn("content: TSiP 是 AI 晶片藍圖。", snippet)

    def test_semantic_retrieve_uses_vision_query_when_attachments_exist(self) -> None:
        state = WorkflowState(user_message="請看圖推薦")
        state.attachments = [
            Attachment(kind="image", content="data:image/png;base64,AAAA", media_type="image/png", name="scan.png")
        ]
        kb = KnowledgeBase(entries=[KnowledgeEntry(id="1", title="支撐鞋", content="支撐型慢跑鞋適合足弓支撐需求。")])
        module = SemanticRetrieve(
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

    def test_generative_action_returns_openai_client_content(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.payload["retrieved_snippet"] = "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"
        with patch(
            "agentic_sdk.llm.openai_compatible.OpenAI",
            return_value=FoundryOpenAILikeClient(action_text="TSiP 是工研院主導的國產 AI 晶片落地藍圖。"),
        ):
            module = GenerativeAction(**_llm_params())

        output = module(state)

        self.assertIsNone(output["next_module"])
        self.assertEqual(
            "TSiP 是工研院主導的國產 AI 晶片落地藍圖。",
            state.last_action_result["content"],
        )

    def test_generative_action_includes_full_conversation_history(self) -> None:
        conversation = InContextMemory(workflow_name="demo", workflow_id="wf-1", session_id="session-1")
        conversation.append_message("user", "第一輪問題")
        conversation.append_message("assistant", "第一輪回答")
        conversation.append_message("user", "第二輪追問")
        state = WorkflowState(user_message="第二輪追問", memory=conversation)
        state.payload["retrieved_snippet"] = "補充檢索內容"
        client = FoundryOpenAILikeClient(action_text="第二輪最終回答")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = GenerativeAction(**_llm_params())

        module(state)

        messages = client.last_create_kwargs["messages"]
        self.assertEqual(["system", "user", "assistant", "user"], [message["role"] for message in messages])
        self.assertEqual("第一輪問題", messages[1]["content"])
        self.assertEqual("第一輪回答", messages[2]["content"])
        self.assertEqual("第二輪追問", messages[3]["content"])

    def test_action_prompt_includes_perceived_context_with_retrieved_context(self) -> None:
        state = WorkflowState(user_message="請推薦鞋墊")
        state.payload["perceived_summary"] = "足測報告顯示足弓指數高，足底局部壓力集中。"
        state.payload["perceived_details"] = {"足弓指數": "高", "壓力分布": "前足集中"}
        state.payload["latest_retrieved_content"] = "科技鞋墊 加強型適合足弓指數高。"
        client = FoundryOpenAILikeClient(action_text="建議科技鞋墊 加強型。")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = GenerativeAction(**_llm_params())

        module(state)

        system_message = client.last_create_kwargs["messages"][0]["content"]
        self.assertIn("perceived_context", system_message)
        self.assertIn("足測報告顯示足弓指數高", system_message)
        self.assertIn("科技鞋墊 加強型適合足弓指數高", system_message)

    def test_tool_call_action_uses_openai_tools_standard(self) -> None:
        state = WorkflowState(user_message="我要預約明天下午三點。")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_booking",
                    "description": "提交預約資料。",
                    "parameters": {
                        "type": "object",
                        "properties": {"customer_name": {"type": "string"}},
                        "required": ["customer_name"],
                    },
                },
            }
        ]
        tool_calls = [
            {
                "id": "call_booking",
                "type": "function",
                "function": {"name": "submit_booking", "arguments": '{"customer_name":"王小明"}'},
            }
        ]
        client = FoundryOpenAILikeClient(action_text="請確認預約資料。", tool_calls=tool_calls)
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = ToolCallAction(tools=tools, **_llm_params())

        output = module(state)

        self.assertIsNone(output["next_module"])
        self.assertEqual(tools, client.last_create_kwargs["tools"])
        self.assertEqual("auto", client.last_create_kwargs["tool_choice"])
        self.assertEqual(tool_calls, output["payload"]["latest_tool_calls"])
        self.assertEqual(tool_calls, state.last_action_result["tool_calls"])

    def test_tool_call_action_omits_tools_when_tool_choice_is_none(self) -> None:
        state = WorkflowState(user_message="請先用文字說明推薦。")
        tools = [{"type": "function", "function": {"name": "submit_api_1", "parameters": {"type": "object"}}}]
        client = FoundryOpenAILikeClient(action_text="建議先採用第一個方案。是否要進入下一步？")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = ToolCallAction(tools=tools, tool_choice="none", **_llm_params())

        output = module(state)

        self.assertNotIn("tools", client.last_create_kwargs)
        self.assertNotIn("tool_choice", client.last_create_kwargs)
        self.assertEqual([], output["payload"]["latest_tool_calls"])
        self.assertEqual("建議先採用第一個方案。是否要進入下一步？", output["payload"]["latest_final_message"])

    def test_tool_call_action_keeps_final_message_when_model_returns_only_tool_calls(self) -> None:
        state = WorkflowState(user_message="我要送出資料。")
        tool_calls = [
            {
                "id": "call_submit",
                "type": "function",
                "function": {"name": "submit_api_1", "arguments": '{"ok":true}'},
            }
        ]
        client = FoundryOpenAILikeClient(action_text="", tool_calls=tool_calls)
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
            module = ToolCallAction(tools=[{"type": "function", "function": {"name": "submit_api_1", "parameters": {"type": "object"}}}], **_llm_params())

        output = module(state)

        self.assertEqual("已產生工具呼叫。", output["payload"]["latest_final_message"])
        self.assertEqual("已產生工具呼叫。", state.last_action_result["content"])
        self.assertEqual(tool_calls, output["payload"]["latest_tool_calls"])

    def test_llm_modules_send_explicit_model(self) -> None:
        perceive_client = FoundryOpenAILikeClient()
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=perceive_client):
            TextPerceive(**_llm_params("perceive-model"))(WorkflowState(user_message="hello"))
        self.assertEqual("perceive-model", perceive_client.last_create_kwargs["model"])

        plan_client = FoundryOpenAILikeClient(plan_sequence=["action"])
        plan_state = WorkflowState(user_message="hello")
        plan_state.append(ContextEntry(type=ContextEntryType.PERCEIVED, content="intent=test", metadata={"intent": "test"}))
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=plan_client):
            NextStepPlan(**_llm_params("plan-model"))(plan_state)
        self.assertEqual("plan-model", plan_client.last_create_kwargs["model"])

        action_client = FoundryOpenAILikeClient(action_text="ok")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=action_client):
            GenerativeAction(**_llm_params("action-model"))(WorkflowState(user_message="hello"))
        self.assertEqual("action-model", action_client.last_create_kwargs["model"])

        reflect_client = FoundryOpenAILikeClient()
        reflect_state = WorkflowState(user_message="hello")
        reflect_state.last_action_result = {"content": "ok"}
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=reflect_client):
            ResponseCheckReflect(**_llm_params("reflect-model"))(reflect_state)
        self.assertEqual("reflect-model", reflect_client.last_create_kwargs["model"])

    def test_llm_module_constructors_require_model_parameter(self) -> None:
        for module_cls in (TextPerceive, TextImagePerceive, NextStepPlan, GenerativeAction, ToolCallAction, ResponseCheckReflect):
            with self.subTest(module=module_cls.__name__):
                with self.assertRaisesRegex(ValueError, "explicit model"):
                    module_cls(api_key=TEST_API_KEY, base_url=TEST_BASE_URL)

    def test_llm_modules_can_build_openai_client_from_explicit_endpoint(self) -> None:
        with patch("agentic_sdk.llm.openai_compatible.OpenAI") as openai_cls:
            openai_cls.return_value = FoundryOpenAILikeClient(action_text="ok")

            GenerativeAction(api_key="ollama", base_url="http://localhost:11434/v1/", model="llama3.2:1b")(
                WorkflowState(user_message="hello")
            )

        openai_cls.assert_called_once_with(api_key="ollama", base_url="http://localhost:11434/v1/")

    def test_llm_modules_require_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit api_key/base_url"):
            GenerativeAction(model="llama3.2:1b")

    def test_removed_outer_layers_are_not_part_of_clean_core(self) -> None:
        self.assertIsNone(importlib.util.find_spec("agentic_sdk.capabilities"))
        self.assertIsNone(importlib.util.find_spec("agentic_sdk.gateway"))
        self.assertIsNone(importlib.util.find_spec("agentic_sdk.knowledge"))

    def test_response_check_reflect_and_evidence_check_reflect_can_pass(self) -> None:
        state = WorkflowState(user_message="TSiP 是什麼？")
        state.last_action_result = {"content": "TSiP 是工研院主導的國產 AI 晶片落地藍圖。"}

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient()):
            response_output = ResponseCheckReflect(**_llm_params())(state)
        evidence_output = EvidenceCheckReflect()(state)

        self.assertIsNone(response_output["next_module"])
        self.assertEqual("pass", response_output["payload"]["reflect_verdict"])
        self.assertIsNone(evidence_output["next_module"])
        self.assertEqual("pass", evidence_output["payload"]["reflect_verdict"])

    def test_evidence_check_reflect_fails_when_retrieve_reports_no_hits(self) -> None:
        state = WorkflowState(user_message="未知問題")
        state.last_action_result = {"content": "目前沒有找到相關參考資料。"}
        state.append(
            ContextEntry(
                type=ContextEntryType.RETRIEVED,
                content="目前沒有找到相關參考資料。",
                metadata={"hit_count": 0},
            )
        )

        output = EvidenceCheckReflect(on_failure="end")(state)

        self.assertIsNone(output["next_module"])
        self.assertEqual("fail", output["payload"]["reflect_verdict"])

    def test_text_perceive_writes_memory_when_memory_store_exists(self) -> None:
        store = InMemoryStore()
        state = WorkflowState(user_message="幫我找鞋")
        state.workflow_name = "test-workflow"
        state.memory_store = store

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient()):
            TextPerceive(**_llm_params())(state)

        entries = store.all_for_workflow("test-workflow")
        self.assertEqual(1, len(entries))
        self.assertEqual("user_input", entries[0].entry_type)

    def test_text_perceive_writes_memory_when_primary_memory_is_persistent(self) -> None:
        store = InMemoryStore(workflow_name="default", workflow_id="wf-1", session_id="session-1")
        store.append_message("user", "幫我找鞋")
        state = WorkflowState(user_message="幫我找鞋", memory=store)

        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient()):
            TextPerceive(**_llm_params())(state)

        entries = [entry for entry in store.all_for_workflow("default") if entry.entry_type == "user_input"]
        self.assertEqual(1, len(entries))
        self.assertEqual("user", entries[0].role)


if __name__ == "__main__":
    unittest.main()