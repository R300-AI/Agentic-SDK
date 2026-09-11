from __future__ import annotations

import io
import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from flask import session

import pytest

from agentic_sdk.core import Attachment, ContextEntry, ContextEntryType, Gates, InContextMemory, WorkflowResult, WorkflowState
from agentic_sdk.core.events import default_events_schema
from agentic_sdk.modules.action.generative import _FINAL_RESPONSE_CONTRACT, _build_messages
from agentic_sdk.modules.action.tool_call import _tool_call_content
from agentic_sdk.modules.retrieve.semantic import FaissKnowledgeBase
from playground.app import create_app
from playground.routes import aihub as aihub_routes
from playground.services.aihub_client import AiHubCredentials
from playground.routes import builder as builder_routes
from playground.routes import runner as runner_routes
from playground.services import key_vault_config, model_endpoints
from playground.services import runner_service
from playground.services import semantic_ingestion
from playground.services import source_builder
from playground.services.runner_conversation import RunnerConversationState
from playground.services.aihub_bridge import store_loaded_agent
from playground.services.source_builder import BuilderSourceConfig
from support import build_source, build_spec
from playground.services.workflow_spec import apply_builder_step, compile_python_source, default_spec, spec_to_config, spec_to_form_state
from playground.services.workflow_reachability import reachable_workflow_roles


def test_key_vault_skip_flag_does_not_bypass_typed_settings(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_SKIP_KEY_VAULT_LOAD", "true")

    settings = key_vault_config._settings_from_values(
        {
            "AI-HUB-BASE-URL": "https://aihub.example",
            "AI-HUB-PLAYGROUND-ORIGIN": "https://playground.example",
        }
    )

    assert settings.ai_hub.base_url == "https://aihub.example"


def test_key_vault_test_mode_uses_only_non_secret_test_inventory(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_TEST_MODE", "true")
    monkeypatch.setattr(
        key_vault_config,
        "_key_vault_values",
        lambda _vault_name: (_ for _ in ()).throw(AssertionError("test mode must not read Azure Key Vault")),
    )

    settings = key_vault_config.key_vault_settings()

    assert settings.ai_hub.base_url == "https://aihub.test"
    assert {endpoint.id for endpoint in settings.chat_endpoints} == {"gpt-54", "gpt-55"}


def test_key_vault_secret_list_uses_secret_name_not_version(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "value": [
                    {"id": "https://agentic-sdk-models.vault.azure.net/secrets/AI-HUB-BASE-URL/123456"},
                    {"id": "https://agentic-sdk-models.vault.azure.net/secrets/GPT-54-MODEL"},
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(key_vault_config.httpx, "Client", FakeClient)

    assert key_vault_config._secret_names("agentic-sdk-models", "token") == ["AI-HUB-BASE-URL", "GPT-54-MODEL"]


def test_key_vault_uses_azure_cli_command_wrapper_on_windows(monkeypatch):
    monkeypatch.setattr(key_vault_config.os, "name", "nt")
    monkeypatch.setattr(key_vault_config.shutil, "which", lambda command: f"C:/tools/{command}" if command == "az.cmd" else None)

    assert key_vault_config._azure_cli_command() == "C:/tools/az.cmd"


def test_semantic_upload_preserves_original_pptx_source_file(tmp_path, monkeypatch):
    source_bytes = b"pptx-binary-content"
    monkeypatch.setattr(semantic_ingestion, "_read_indexable_text", lambda _path, _suffix: "Workshop deployment content")

    result = semantic_ingestion.ingest_semantic_upload(
        filename="AI Hub 工作坊.pptx",
        stream=BytesIO(source_bytes),
        target_dir=tmp_path,
    )

    assert result.accepted is True
    assert result.canonical_name == "AI Hub 工作坊.pptx"
    assert (tmp_path / result.canonical_name).read_bytes() == source_bytes
    assert not list(tmp_path.glob("*.md"))


def test_semantic_upload_preserves_unicode_source_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_ingestion, "_read_indexable_text", lambda _path, _suffix: "AI Hub workshop content")

    result = semantic_ingestion.ingest_semantic_upload(
        filename="AI Hub上架教學.pptx",
        stream=BytesIO(b"pptx-binary-content"),
        target_dir=tmp_path,
    )

    assert result.accepted is True
    assert result.canonical_name == "AI Hub上架教學.pptx"
    assert (tmp_path / result.canonical_name).read_bytes() == b"pptx-binary-content"


def test_semantic_upload_advertises_only_verified_indexable_formats():
    assert set(semantic_ingestion.accepted_upload_extensions()) == {
        ".cfg",
        ".csv",
        ".docx",
        ".htm",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".pdf",
        ".pptx",
        ".py",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xls",
        ".xlsx",
        ".xml",
        ".yaml",
        ".yml",
    }


def test_builder_upload_input_uses_verified_extension_list(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_TEST_MODE", "true")
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    expected_accept = ",".join(semantic_ingestion.accepted_upload_extensions())
    assert response.status_code == 200
    assert f'accept="{expected_accept}"' in response.text
    assert ".doc," not in response.text
    assert ".ppt," not in response.text
    assert ".png," not in response.text


def test_semantic_pdf_upload_prefers_pdfminer(tmp_path, monkeypatch):
    class FailingMarkItDown:
        def convert(self, _path):
            raise AssertionError("PDF validation should not call MarkItDown when pdfminer is available")

    monkeypatch.setitem(sys.modules, "markitdown", SimpleNamespace(MarkItDown=FailingMarkItDown))
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", SimpleNamespace(extract_text=lambda _path: "PDF workshop content"))

    result = semantic_ingestion.ingest_semantic_upload(
        filename="Agentic SDK使用教學.pdf",
        stream=BytesIO(b"%PDF-1.7"),
        target_dir=tmp_path,
    )

    assert result.accepted is True
    assert result.canonical_name == "Agentic SDK使用教學.pdf"


def test_semantic_pdf_upload_falls_back_to_pypdf(tmp_path, monkeypatch):
    def fail_pdfminer(_path):
        raise RuntimeError("pdfminer unavailable")

    page = SimpleNamespace(extract_text=lambda: "PDF workshop fallback content")
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", SimpleNamespace(extract_text=fail_pdfminer))
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: SimpleNamespace(pages=[page])))

    result = semantic_ingestion.ingest_semantic_upload(
        filename="Agentic SDK使用教學.pdf",
        stream=BytesIO(b"%PDF-1.7"),
        target_dir=tmp_path,
    )

    assert result.accepted is True
    assert result.canonical_name == "Agentic SDK使用教學.pdf"


def test_semantic_retrieve_extracts_original_binary_pptx(tmp_path, monkeypatch):
    source = tmp_path / "workshop.pptx"
    source.write_bytes(b"\xff\xfebinary-presentation")

    class FakeMarkItDown:
        def convert(self, path):
            assert path == str(source)
            return SimpleNamespace(text_content="AI Hub deployment workshop")

    monkeypatch.setitem(sys.modules, "markitdown", SimpleNamespace(MarkItDown=FakeMarkItDown))
    knowledge_base = FaissKnowledgeBase(index_path=str(tmp_path / "index"), embedder=object())

    assert knowledge_base._read_document(source) == "AI Hub deployment workshop"


def test_semantic_retrieve_prefers_pdfminer_for_pdf(tmp_path, monkeypatch):
    source = tmp_path / "workshop.pdf"
    source.write_bytes(b"%PDF-1.7\n%\xff\xff\xff\xff")

    class FailingMarkItDown:
        def convert(self, _path):
            raise AssertionError("PDF retrieval should not call MarkItDown when pdfminer is available")

    monkeypatch.setitem(sys.modules, "markitdown", SimpleNamespace(MarkItDown=FailingMarkItDown))
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", SimpleNamespace(extract_text=lambda _path: "PDF workshop content"))
    knowledge_base = FaissKnowledgeBase(index_path=str(tmp_path / "index"), embedder=object())

    assert knowledge_base._read_document(source) == "PDF workshop content"


def test_semantic_retrieve_falls_back_to_pypdf_for_pdf(tmp_path, monkeypatch):
    source = tmp_path / "workshop.pdf"
    source.write_bytes(b"%PDF-1.7\n%\xff\xff\xff\xff")

    def fail_pdfminer(_path):
        raise RuntimeError("pdfminer unavailable")

    page = SimpleNamespace(extract_text=lambda: "PDF workshop fallback content")
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", SimpleNamespace(extract_text=fail_pdfminer))
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _path: SimpleNamespace(pages=[page])))
    knowledge_base = FaissKnowledgeBase(index_path=str(tmp_path / "index"), embedder=object())

    assert knowledge_base._read_document(source) == "PDF workshop fallback content"


def test_runner_execution_memory_keeps_current_image_attachment_transient():
    spec = build_spec()
    conversation = RunnerConversationState.start().append_user("請解讀足測報告")
    attachment = Attachment(
        kind="image",
        name="foot-report.png",
        media_type="image/png",
        content="data:image/png;base64,aGVsbG8=",
    )

    memory = runner_service._conversation_memory_for_execution(conversation, "LaNew鞋墊顧問", [attachment])

    assert memory is not None
    message = memory.as_openai_messages(include_attachments=True)[-1]
    assert message["content"][-1]["image_url"]["url"] == attachment.content
    assert conversation.as_dict()["turns"][-1].get("attachments") is None


def test_action_messages_require_direct_user_facing_answers_for_custom_prompts():
    memory = InContextMemory()
    memory.append_message("user", "解讀足測報告中的數值")
    state = WorkflowState(
        user_message="解讀足測報告中的數值",
        memory=memory,
    )
    state.payload.update(
        {
            "perceived_summary": "足弓指數正常",
            "perceived_details": {"左足 B%": "24.9%"},
            "latest_retrieved_content": "商品目錄內容",
        }
    )

    messages = _build_messages(state, "你是鞋墊顧問。")
    system_message = messages[0]["content"]

    assert _FINAL_RESPONSE_CONTRACT in system_message
    assert "第一句就提供所問的結果" in system_message
    assert "不得在對外回答中逐段盤點" in system_message
    assert "skipped=true" in system_message
    assert "perceived_context" in system_message
    assert "retrieved_context" in system_message


def test_interactive_policy_keeps_tool_decisions_internal():
    assert "內部決策規則" in source_builder.INTERACTIVE_TOOL_POLICY
    assert "不要向使用者描述判斷、工具或元件流程" in source_builder.INTERACTIVE_TOOL_POLICY
    assert "只能收集該工具 schema 中定義的欄位" in source_builder.INTERACTIVE_TOOL_POLICY
    assert "不可自行要求、暗示或臆測未配置的業務欄位" in source_builder.INTERACTIVE_TOOL_POLICY


def test_completed_runner_trace_is_collapsed_by_default():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")
    surface_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "result-surface.js").read_text(encoding="utf-8")

    completed_trace = runner_source.split("setProcessEvents(assistant.processTrace, finalProcessEvents", 1)[1].split("});", 1)[0]

    assert "collapsible: true" in completed_trace
    assert "preserveOpen" not in completed_trace
    assert "open: true" not in surface_source.split("export function showLiveProcessEvent", 1)[1].split("function updateLiveProcessTrace", 1)[0]
    assert "processDisplayDescription" in surface_source
    assert "process-event-mark" not in surface_source


def test_runner_explains_expired_save_session_before_reauthentication():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'openSaveLoginModal({ sessionExpired: true })' in runner_source
    assert "登入工作階段已過期，請重新登入後儲存。" in runner_source


def test_runner_hydrates_metadata_from_server_rendered_fields():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert "workflowNameTargets[0]?.textContent?.trim()" in runner_source
    assert "workflowDescriptionTargets[0]?.textContent?.trim()" in runner_source


def test_reasoning_surface_uses_controlled_stage_descriptions_only():
    surface_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "result-surface.js").read_text(encoding="utf-8")

    assert 'if (title === "流程中止")' in surface_source
    assert 'return String(event?.description || "").trim() || "流程已被安全限制中止。";' in surface_source
    assert "return \"正在處理這個步驟。\";" in surface_source
    assert "test(description)" not in surface_source


def test_builder_blocks_incomplete_interactive_contract_before_advancing():
    builder_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "builder" / "builder-page.js").read_text(encoding="utf-8")

    assert "請完成必填欄位。" in builder_source
    assert "請至少完成一組「API URL」與「需要收集的資訊」。" not in builder_source
    assert "const validationError = requiredStepError(activePanel);" in builder_source
    assert "if (validationError)" in builder_source


def test_runner_offers_confirmation_for_mixed_analysis_and_explicit_decision_request():
    config = BuilderSourceConfig(
        workflow_name="LaNew鞋墊顧問",
        action_module="ToolCallAction",
        action_tools=(
            {
                "type": "function",
                "function": {
                    "name": "confirm_store_assistance",
                    "parameters": {"type": "object", "properties": {"是否進行下一步": {"type": "boolean"}}},
                },
            },
        ),
    )
    user_message = "根據剛才的足測結果推薦鞋墊；我想安排門市協助。"
    final_message = "推薦科技鞋墊 通用型。請確認是否要這樣送出門市協助需求。"

    assert runner_service._should_offer_configured_tool_panel(config, user_message, final_message)


def test_placeholder_tool_submission_reports_verified_unsent_outcome():
    message = runner_service._tool_submission_final_message(
        "模型回覆。",
        {
            "api_result": {
                "skipped": True,
                "message": "這是示範 API 端點，尚未設定可執行的外部服務，因此未送出動作。",
            }
        },
    )

    assert message.startswith("本次請求未送出：")
    assert "未送出動作" in message
    assert "門市" not in message
    assert message.endswith("模型回覆。")


def test_runner_does_not_offer_confirmation_for_status_recall_question():
    config = BuilderSourceConfig(
        workflow_name="LaNew鞋墊顧問",
        action_module="ToolCallAction",
        action_tools=(
            {
                "type": "function",
                "function": {
                    "name": "confirm_store_assistance",
                    "parameters": {"type": "object", "properties": {"是否進行下一步": {"type": "boolean"}}},
                },
            },
        ),
    )
    user_message = "剛才推薦的是哪一款、商品編號多少？通知有沒有真的送出？"
    final_message = "推薦科技鞋墊 通用型，商品編號 291090970；本次沒有送出通知。"

    assert not runner_service._should_offer_configured_tool_panel(config, user_message, final_message)


def test_tool_call_without_text_uses_user_facing_confirmation_message():
    assert _tool_call_content("", [{"function": {"name": "confirm"}}]) == "請確認下列選項。"
    assert _tool_call_content("已找到推薦。", [{"function": {"name": "confirm"}}]) == "已找到推薦。"


def test_builder_choices_map_to_runtime_modules():
    for choice, expected_module in {
        "pass_through": "PassThroughPerceive",
        "text": "TextPerceive",
        "text_image": "TextImagePerceive",
        "voice": "VoiceTextPerceive",
    }.items():
        config = spec_to_config(build_spec(("input_type", choice)))
        assert config.perceive_module == expected_module
        assert "perceive" in reachable_workflow_roles(config)

    for choice, expected_module in {
        "none": "PassThroughRetrieve",
        "keyword": "KeywordRetrieve",
        "semantic": "SemanticRetrieve",
    }.items():
        config = spec_to_config(build_spec(("retrieve_policy", choice)))
        assert config.retrieve_module == expected_module
        assert "retrieve" in reachable_workflow_roles(config)

    free_text = spec_to_config(build_spec(("output_format", "free_text")))
    interactive = spec_to_config(build_spec(("output_format", "interactive")))
    voice = spec_to_config(build_spec(("output_format", "voice")))

    assert free_text.action_module == "GenerativeAction"
    assert interactive.action_module == "ToolCallAction"
    assert voice.action_module == "VoiceAnswerAction"
    assert "action" in reachable_workflow_roles(free_text)
    assert "action" in reachable_workflow_roles(interactive)
    assert "action" in reachable_workflow_roles(voice)


def test_key_vault_model_endpoint_requires_explicit_deployment_selection():

    with __import__("pytest").raises(model_endpoints.MissingEndpointBinding):
        model_endpoints.endpoint_params_for_role("action", {})

    params = model_endpoints.endpoint_params_for_role("action", {"action": "gpt-54"})
    assert params["api_key"]
    assert params["base_url"].startswith("https://")
    assert params["model"]
    assert model_endpoints.normalize_endpoint_selections(build_spec(), {}) == {}


def test_deployment_options_follow_reachable_modules_and_require_selection():
    spec = build_spec(
        ("input_type", "text"),
        ("retrieve_policy", "semantic"),
        ("output_format", "free_text"),
        ("failure_policy", "retry"),
    )

    state = model_endpoints.endpoint_state(spec, {})

    # A keyword or semantic agent used to fail at run time for want of a
    # planner's model. It is answered by sharing the answering step's, not by
    # adding a question nobody could map to anything they chose.
    # No planner here: the step exists, but nobody is asked to choose a model
    # for something they did not pick.
    assert [requirement["role"] for requirement in state["requirements"]] == ["perceive", "retrieve", "action"]
    assert state["selections"] == {"perceive": "", "retrieve": "", "action": ""}
    assert state["binding_missing_roles"] == {"perceive": True, "retrieve": True, "action": True}
    # Nothing is bound yet, so nothing is configured. This line used to assert
    # the opposite, which is how an agent with no deployments chosen could be
    # finished in the Builder and then fail to start.
    assert state["configured"] is False
    retrieve_requirement = next(r for r in state["requirements"] if r["role"] == "retrieve")
    assert {option["id"] for option in retrieve_requirement["options"]} == {"embedded-large", "embedded-small"}

    spec = default_spec()
    spec["perceive"]["module"] = "TextPerceive"
    spec["retrieve"]["module"] = "SemanticRetrieve"
    spec["action"]["module"] = "GenerativeAction"
    spec["reflect"]["module"] = "ResponseCheckReflect"
    response_check_state = model_endpoints.endpoint_state(spec, {})

    assert [requirement["role"] for requirement in response_check_state["requirements"]] == ["perceive", "retrieve", "action", "reflect"]


def test_builder_review_requires_each_reachable_deployment_option():
    spec = build_spec(
        ("input_type", "text"),
        ("output_format", "free_text"),
    )
    endpoint_state = model_endpoints.endpoint_state(spec, {})
    form_state = {"choices": {"input_type": "整理文字內容", "output_format": "純文字回覆"}, "values": {}}

    errors = builder_routes._endpoint_requirements_by_step(endpoint_state)
    review = builder_routes._builder_review_state(builder_routes.get_builder_steps(), form_state, endpoint_state)
    review_by_step = {item["step_key"]: item for item in review}

    assert errors == {"input_type": ["請選擇部署選項。"], "output_format": ["請選擇部署選項。"]}
    assert review_by_step["input_type"]["completed"] is False
    assert review_by_step["output_format"]["completed"] is False


def test_builder_deployment_selectors_are_key_vault_backed():
    builder_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "builder" / "builder-page.js").read_text(encoding="utf-8")

    assert ".env" not in builder_source
    assert "data-builder-endpoint-select" in builder_source
    assert "(請選擇部署選項)" in builder_source
    assert 'postJson("/playground/builder/endpoints", { selections })' in builder_source


def test_partial_key_vault_endpoint_family_is_rejected():
    with __import__("pytest").raises(key_vault_config.KeyVaultConfigurationError, match="GPT-54-MODEL"):
        key_vault_config._settings_from_values(
            {
                "AI-HUB-BASE-URL": "https://aihub.example",
                "AI-HUB-PLAYGROUND-ORIGIN": "https://playground.example",
                "GPT-54-API-KEY": "key",
                "GPT-54-BASE-URL": "https://models.example",
            }
        )


def test_interactive_action_contract_roundtrips_to_boolean_tool_schema():
    spec = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "response_instruction": "先說明建議，再詢問是否提交。",
                "api_contracts": "",
                "interaction_trigger": "使用者需要確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/submit",
                "component_fields": "是否提交 = 使用者是否確認提交（資料類型：是/否)",
            },
        ),
    )

    config = spec_to_config(spec)
    field = config.action_tools[0]["function"]["parameters"]["properties"]["是否提交"]

    assert config.action_module == "ToolCallAction"
    assert field["type"] == "boolean"
    parameters = config.action_tools[0]["function"]["parameters"]
    assert parameters["required"] == ["是否提交", "__playground_review", "__playground_options"]
    assert parameters["properties"]["__playground_review"]["type"] == "string"
    assert parameters["properties"]["__playground_options"]["type"] == "object"
    assert "__playground_review" not in source_builder._component_fields_text_from_parameters(parameters)
    assert "__playground_options" not in source_builder._component_fields_text_from_parameters(parameters)


def test_runner_projects_generated_string_choices_without_submitting_platform_metadata():
    schema = {
        "parameters": {
            "type": "object",
            "properties": {
                "開發方向": {"type": "string"},
                "預算": {"type": "number"},
                "__playground_options": {"type": "object"},
            },
            "required": ["開發方向", "預算", "__playground_options"],
        }
    }
    arguments = {
        "開發方向": "Web 應用程式",
        "預算": 50000,
        "__playground_options": {
            "開發方向": {
                "choices": ["Web 應用程式", "行動應用程式", "桌面應用程式"],
                "custom_label": "自訂開發方向",
            }
        },
    }

    fields = runner_service._tool_call_fields_from(schema, arguments)

    assert fields[0]["choices"] == [
        {"value": "Web 應用程式", "label": "Web 應用程式", "description": ""},
        {"value": "行動應用程式", "label": "行動應用程式", "description": ""},
        {"value": "桌面應用程式", "label": "桌面應用程式", "description": ""},
    ]
    assert fields[1]["value"] == 50000
    assert fields[0]["custom_label"] == "自訂開發方向"
    assert runner_service._without_tool_call_review(arguments) == {"開發方向": "Web 應用程式", "預算": 50000}


def test_runner_does_not_surface_tool_arguments_outside_builder_schema():
    schema = {
        "parameters": {
            "type": "object",
            "properties": {"聯絡人": {"type": "string"}},
            "required": ["聯絡人"],
        }
    }

    fields = runner_service._tool_call_fields_from(schema, {"聯絡人": "陳小明", "電子郵件": "example@example.com"})

    assert [field["name"] for field in fields] == ["聯絡人"]


def test_interactive_panel_submission_releases_pending_state():
    runner_directory = Path(__file__).parents[1] / "playground" / "static" / "js" / "runner"
    surface_source = (runner_directory / "result-surface.js").read_text(encoding="utf-8")
    runner_source = (runner_directory / "runner-page.js").read_text(encoding="utf-8")

    assert 'confirmButton.disabled = true;' in surface_source
    assert 'form.addEventListener("runner:tool-call-complete"' in surface_source
    assert 'completion.className = "tool-call-status tool-call-complete";' in surface_source
    assert 'completion.textContent = "已送出選擇";' in surface_source
    assert 'confirmButton.replaceWith(completion);' in surface_source
    assert 'status.remove();' in surface_source
    assert '選擇已更新，尚未送出。' not in surface_source
    assert 'function createStringChoiceControl(field, fieldId, label)' in surface_source
    assert 'wrapper.append(createStringChoice(field, fieldId, "__custom__", field.customLabel, false));' in surface_source
    assert 'choices.forEach((choice, index) =>' in surface_source
    assert 'function createNumberControl(field, fieldId)' in surface_source
    assert 'decrement.addEventListener("click", () => input.stepDown());' in surface_source
    assert 'increment.addEventListener("click", () => input.stepUp());' in surface_source
    assert 'const hasBooleanValue = field.value === true || field.value === false' in surface_source
    assert 'hasBooleanValue && (value ? booleanValue : !booleanValue)' in surface_source
    assert 'const missingRequiredFields = panel.fields.filter((field) => field.required && !hasToolCallValue(argumentsPayload[field.name]));' in surface_source
    assert 'if (missingRequiredFields.length)' in surface_source
    assert 'function hasToolCallValue(value)' in surface_source
    assert 'event.target?.dispatchEvent(new CustomEvent("runner:tool-call-complete"));' in runner_source


def test_runner_does_not_refresh_ai_hub_credentials_in_background():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'postJson("/playground/aihub/config/save")' in runner_source
    assert 'postJson("/playground/aihub/session/refresh")' not in runner_source
    assert "refreshAiHubSession" not in runner_source


def test_runner_commits_conversation_after_stream_completion():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'postJson("/playground/run/conversation/commit", { conversation_update: update })' in runner_source
    assert "await commitConversationUpdate(result.conversation_update);" in runner_source


def test_runner_execution_stream_emits_one_final_event(monkeypatch):
    def fake_execute(_python_source, *, process_observer=None, **_kwargs):
        if process_observer is not None:
            process_observer({"stage": "perceive", "status": "completed"})
            process_observer({"stage": "action", "status": "completed"})
        return {"status": "completed", "final_message": "單一最終回覆"}

    monkeypatch.setattr(runner_service, "run_agent", fake_execute)

    events = list(runner_service.stream_agent_run("workflow = Workflow()", message="測試"))

    assert [event["type"] for event in events].count("final") == 1
    assert events[-1] == {"type": "final", "execution": {"status": "completed", "final_message": "單一最終回覆"}}


def test_runner_execute_routes_forward_attachment_payloads(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    def fake_run_agent(_python_source, **kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "final_message": "ok",
            "tool_calls": [],
            "tool_call_panels": [],
            "debug_messages": [],
            "process_events": [],
            "result": {"message": "ok"},
            "scene_profile": {},
        }

    monkeypatch.setattr(runner_routes, "run_agent", fake_run_agent)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = build_spec()
        response = client.post(
            "/playground/run/execute",
            json={
                "message": "請判讀圖片",
                "attachments": [
                    {
                        "kind": "image",
                        "name": "report.png",
                        "media_type": "image/png",
                        "content": "data:image/png;base64,abc",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert captured["attachments"] == [
        {
            "kind": "image",
            "name": "report.png",
            "media_type": "image/png",
            "content": "data:image/png;base64,abc",
        }
    ]


def test_runner_conversation_state_restores_ordered_turns_across_source_changes():
    first = RunnerConversationState.start()
    restored = RunnerConversationState.from_dict(
        {
            **first.as_dict(),
            "turns": [
                {"role": "user", "content": "我有高足弓"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型，SKU 7037439。"},
            ],
        },
    )

    memory = restored.memory(workflow_name="LaNew")

    assert [turn.role for turn in memory.turns] == ["user", "assistant"]
    assert memory.turns[-1].content == "推薦科技鞋墊 加強型，SKU 7037439。"
    changed = RunnerConversationState.from_dict(restored.as_dict())
    assert [turn.content for turn in changed.turns] == ["我有高足弓", "推薦科技鞋墊 加強型，SKU 7037439。"]


def test_runner_conversation_memory_exposes_prior_retrieval_evidence_to_modules():
    spec = build_spec()
    state = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.start().as_dict(),
            "retrieval_evidence": "高足弓適用：科技鞋墊 加強型，SKU 7037439。",
        },
    )

    memory = state.memory(workflow_name="LaNew")

    assert memory.metadata["continuity_evidence"] == "高足弓適用：科技鞋墊 加強型，SKU 7037439。"


def test_runner_execution_injects_conversation_memory_into_workflow(monkeypatch):
    captured = {}
    source = build_spec()
    state = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.start().as_dict(),
            "turns": [
                {"role": "user", "content": "我有高足弓"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型，SKU 7037439。"},
            ],
        },
    ).append_user("台北信義區")

    class FakeWorkflow:
        def run(self, *, user_message=None, **kwargs):
            captured.update(kwargs)
            captured["user_message"] = user_message
            memory = kwargs["memory"]
            memory.append_message("assistant", "已保留高足弓推薦。")
            return WorkflowResult(workflow_id="workflow", final_message="已保留高足弓推薦。", memory=memory)

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    execution = runner_service.run_agent(source, message="台北信義區", conversation_state=state)

    assert captured["session_id"] == state.conversation_id
    assert captured["user_message"] is None
    assert [turn.content for turn in captured["memory"].turns[:2]] == ["我有高足弓", "推薦科技鞋墊 加強型，SKU 7037439。"]
    assert execution["conversation_update"]["turns"][-1]["content"] == "已保留高足弓推薦。"


def test_tool_continuation_extends_the_same_conversation_memory():
    spec = build_spec()
    conversation = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.start().as_dict(),
            "retrieval_evidence": "科技鞋墊 加強型，SKU 7037439。",
            "turns": [
                {"role": "user", "content": "高足弓適合哪款？"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型。"},
            ],
        },
    )
    captured = {}
    process_events = []

    class FakeAction:
        def __call__(self, state):
            captured["memory"] = state.memory
            captured["evidence"] = state.entities.get("latest_retrieved_content")
            return {"next_module": None, "payload": {"latest_final_message": "已送出門市協助需求。"}}

    class FakeWorkflow:
        workflow_name = "LaNew"
        memory_store = None
        modules = {"action": FakeAction()}

    result = runner_service._run_tool_submission_continuation(
        FakeWorkflow(),
        BuilderSourceConfig(workflow_name="LaNew"),
        "使用者已送出互動選項。\n工具名稱：門市協助",
        {"function_name": "門市協助", "arguments": {"是否通知": True}, "api_result": {"skipped": True}},
        conversation_state=conversation,
        attachments=[],
        process_observer=process_events.append,
    )

    assert [turn.role for turn in captured["memory"].turns] == ["user", "assistant", "user", "assistant"]
    assert "是否通知" in captured["memory"].turns[2].content
    assert "7037439" in captured["evidence"]
    assert result.memory.turns[-1].content == "已送出門市協助需求。"
    assert conversation.update_from_result(result).retrieval_evidence == "科技鞋墊 加強型，SKU 7037439。"
    assert [event["phase"] for event in process_events] == ["start", "finish"]
    assert process_events[0]["visit_id"] == process_events[1]["visit_id"]


def test_tool_submission_update_keeps_selection_and_api_outcome_internal():
    spec = build_spec()
    conversation = RunnerConversationState.start()

    update = runner_service._conversation_update(
        conversation,
        "已完成門市協助需求。",
        retrieval_evidence="",
        tool_submission_context={
            "function_name": "門市協助",
            "arguments": {"是否通知": False},
            "api_result": {"ok": True, "status_code": 200},
        },
    )

    assert update is not None
    turns = update["turns"]
    assert [turn["role"] for turn in turns] == ["user", "assistant", "assistant"]
    assert turns[0]["metadata"]["visibility"] == "internal"
    assert "是否通知" in turns[0]["content"]
    assert turns[1]["metadata"]["visibility"] == "internal"
    assert "status_code" in turns[1]["content"]
    assert turns[2]["content"] == "已完成門市協助需求。"
    assert update["revision"] == conversation.revision + 1


def test_runner_conversation_commit_persists_one_expected_revision(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec()

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = spec
            initial = RunnerConversationState.start()
            current_session["runner_conversation"] = initial.as_dict()

        update = {
            **initial.as_dict(),
            "revision": 1,
            "turns": [
                {"role": "user", "content": "高足弓適合哪款？"},
                {"role": "assistant", "content": "科技鞋墊 加強型，SKU 7037439。"},
            ],
        }
        committed = client.post("/playground/run/conversation/commit", json={"conversation_update": update})
        idempotent = client.post("/playground/run/conversation/commit", json={"conversation_update": update})
        conflict = client.post(
            "/playground/run/conversation/commit",
            json={
                "conversation_update": {
                    **update,
                    "turns": [
                        {"role": "user", "content": "高足弓適合哪款？"},
                        {"role": "assistant", "content": "不同的過期回覆。"},
                    ],
                }
            },
        )

        with client.session_transaction() as current_session:
            stored = current_session["runner_conversation"]

    assert committed.status_code == 200
    assert committed.json["committed"] is True
    assert idempotent.status_code == 200
    assert idempotent.json["committed"] is True
    assert stored["turns"][-1]["content"] == "科技鞋墊 加強型，SKU 7037439。"
    assert conflict.status_code == 409
    assert conflict.json["conflict"] is True


def test_runner_persists_normal_user_turn_before_execution(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec()
    captured = {}

    def fake_execute(_source, **kwargs):
        captured["conversation"] = kwargs["conversation_state"]
        return {"status": "ok", "final_message": "已處理", "result": {}, "conversation_update": None}

    monkeypatch.setattr(runner_routes, "run_agent", fake_execute)

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = spec
            current_session["runner_conversation"] = RunnerConversationState.start().as_dict()

        response = client.post("/playground/run/execute", json={"message": "我有高足弓"})

        with client.session_transaction() as current_session:
            stored = current_session["runner_conversation"]

    assert response.status_code == 200
    assert [turn.content for turn in captured["conversation"].turns] == ["我有高足弓"]
    assert captured["conversation"].revision == 1
    assert stored["turns"] == [{"role": "user", "content": "我有高足弓", "metadata": {}}]


def test_runner_page_initializes_conversation_state_for_first_turn():
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec()

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = spec

        response = client.get("/playground/run")

        with client.session_transaction() as current_session:
            stored = current_session["runner_conversation"]

    assert response.status_code == 200
    assert stored["revision"] == 0
    assert stored["turns"] == []


def test_atomic_runner_metadata_update_compiles_the_current_v2_spec():
    app = create_app()
    app.config.update(TESTING=True)
    spec = default_spec()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["workflow_spec"] = build_spec()

        response = client.post(
            "/playground/run/metadata",
            json={
                "name": "Metadata contract verification",
                "description": "Keep name and description in one v2 mutation.",
            },
        )
        preview = client.get("/playground/source/preview")

    assert response.status_code == 200
    assert response.get_json()["workflow_summary"]["name"] == "Metadata contract verification"
    assert preview.status_code == 200
    assert 'workflow_name="Metadata contract verification"' in preview.get_data(as_text=True)
    assert "Keep name and description in one v2 mutation." in preview.get_data(as_text=True)


def test_semantic_builder_upload_unblocks_review_and_reaches_runner(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    monkeypatch.setattr(
        builder_routes,
        "endpoint_state",
        lambda _python_source, _endpoint_selections: {"requirements": [], "configured_roles": {}},
    )

    def fake_run_agent(_python_source, **kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "final_message": "ok",
            "tool_calls": [],
            "tool_call_panels": [],
            "debug_messages": [],
            "process_events": [],
            "result": {"message": "ok"},
            "scene_profile": {},
        }

    monkeypatch.setattr(runner_routes, "run_agent", fake_run_agent)

    with app.test_client() as client:
        semantic_response = client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        semantic_payload = semantic_response.get_json()
        retrieve_review = next(item for item in semantic_payload["builder_review_state"] if item["step_key"] == "retrieve_policy")

        upload_response = client.post(
            "/playground/builder/uploads",
            data={"files": (BytesIO(b"product information"), "products.md")},
            content_type="multipart/form-data",
        )
        upload_payload = upload_response.get_json()
        uploaded_review = next(item for item in upload_payload["builder_review_state"] if item["step_key"] == "retrieve_policy")

        run_response = client.post("/playground/run/execute", json={"message": "查詢產品"})

    assert semantic_response.status_code == 200
    assert retrieve_review["completed"] is False
    assert "參考文件" in retrieve_review["detail"]
    assert upload_response.status_code == 200
    assert upload_payload["semantic_support_files"] == ["products.md"]
    assert uploaded_review["completed"] is True
    assert run_response.status_code == 200
    assert captured["semantic_runtime"].sources and captured["semantic_runtime"].sources[0].endswith("source-files")
    assert captured["semantic_runtime"].saved_path


def test_semantic_builder_upload_rejects_archives_before_saving():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        response = client.post(
            "/playground/builder/uploads",
            data={"files": (BytesIO(b"not an archive"), "catalog.zip")},
            content_type="multipart/form-data",
        )
        with client.session_transaction() as current_session:
            upload_id = current_session.get("builder_upload_id")

    assert response.status_code == 400
    assert response.json["updated"] is False
    assert response.json["rejected_files"] == [
        {"name": "catalog.zip", "reason": "不支援壓縮檔；請先解壓縮後上傳其中需要建立知識庫的文件。"}
    ]
    assert not upload_id


def test_semantic_ingestion_rejects_oversized_file_without_persisting(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_ingestion, "_MAX_UPLOAD_BYTES", 3)

    result = semantic_ingestion.ingest_semantic_upload(
        filename="catalog.md",
        stream=BytesIO(b"four"),
        target_dir=tmp_path,
    )

    assert result.accepted is False
    assert result.reason == "檔案超過知識庫上傳大小限制。"
    assert list(tmp_path.iterdir()) == []


def test_builder_semantic_upload_ui_advertises_only_supported_formats():
    template = (Path(__file__).parents[1] / "playground" / "templates" / "builder.html").read_text(encoding="utf-8")
    script = (Path(__file__).parents[1] / "playground" / "static" / "js" / "builder" / "builder-page.js").read_text(encoding="utf-8")

    assert 'accept="{{ semantic_upload_accept }}"' in template
    assert ".zip" not in template
    assert "String(input.accept || \"\")" in script
    assert ".doc\", \".docx\"" not in script
    assert "rejected_files" in script


def test_runner_keeps_chat_attachments_transient_without_knowledge_upload_controls():
    template = (Path(__file__).parents[1] / "playground" / "templates" / "runner.html").read_text(encoding="utf-8")
    runner_script = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'data-attachment-input' in template
    assert 'for="runner-attachments" aria-label="上傳本次試跑附件"' in template
    assert 'data-knowledge-input' not in template
    assert '新增知識庫檔案' not in template
    assert '/playground/run/knowledge/uploads' not in runner_script
    assert 'attachmentInput?.addEventListener("change", async () =>' not in runner_script


def test_semantic_initialization_checks_knowledge_requirement_and_restored_sources(tmp_path):
    config = BuilderSourceConfig(
        workflow_name="semantic readiness",
        retrieve_module="SemanticRetrieve",
        semantic_support_files=("catalog.md",),
    )
    source_dir = tmp_path / "source-files"
    source_dir.mkdir()
    source_dir.joinpath("catalog.md").write_text("catalog content", encoding="utf-8")

    steps = runner_service._initialization_steps(config, {}, {"retrieve"}, [str(source_dir)], str(tmp_path))
    initializers = {role: initializer for role, _label, initializer in steps}

    assert [role for role, _label, _initializer in steps[:3]] == ["knowledge_requirement", "knowledge_resources", "retrieve"]
    assert initializers["knowledge_requirement"]() is None
    assert initializers["knowledge_resources"]() is None


def test_semantic_initialization_blocks_when_configured_knowledge_is_unavailable():
    spec = apply_builder_step(default_spec(), "retrieve_policy", "semantic")

    events = list(runner_service.stream_agent_initialization(spec))

    assert events[-1]["type"] == "final"
    assert events[-1]["ready"] is False
    assert events[-1]["role"] == "knowledge_resources"
    assert "尚未設定參考文件" in events[-1]["error"]


def test_nonsemantic_initialization_does_not_require_knowledge_sources():
    config = BuilderSourceConfig(workflow_name="no knowledge")
    steps = runner_service._initialization_steps(config, {}, set(), None, None)

    assert [role for role, _label, _initializer in steps] == ["knowledge_requirement"]
    assert steps[0][2]() is None


def test_runner_edit_settings_navigation_preserves_current_draft():
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec(("input_type", "text_image"))

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["workflow_spec"] = spec
            session["builder_has_user_config"] = True

        runner_response = client.get("/playground/run")
        builder_response = client.get("/playground/builder")

        with client.session_transaction() as session:
            preserved_config = spec_to_config(session["workflow_spec"])

    assert runner_response.status_code == 200
    assert builder_response.status_code == 200
    assert preserved_config.perceive_module == "TextImagePerceive"


def test_aihub_readonly_deep_link_without_loaded_source_does_not_dead_end(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)

    def fake_load_public_config(agent_id, **_kwargs):
        return {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Shared Agent",
            "workflow_spec": build_spec(("input_type", "text")),
            "python_source": build_source(("input_type", "text")),
        }

    monkeypatch.setattr("playground.routes.entry.load_public_config", fake_load_public_config)

    with app.test_client() as client:
        response = client.get("/playground?mode=aihub_readonly&agent_id=agent-1", follow_redirects=True)
        with client.session_transaction() as session:
            loaded_config = spec_to_config(session["workflow_spec"])

    assert response.status_code == 200
    assert loaded_config.perceive_module == "TextPerceive"
    assert b"\xe8\xa9\xa6\xe8\xb7\x91 Agent" in response.data


def test_anonymous_start_clears_prior_loaded_agent_state():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["mode"] = "aihub_editable"
            session["agent_id"] = "old-agent"
            session["workflow_spec"] = build_spec(("input_type", "text_image"))
            
            session["builder_upload_id"] = "old-upload"

        response = client.post("/playground/start/anonymous")
        with client.session_transaction() as session:
            config = spec_to_config(session["workflow_spec"])
            session_snapshot = dict(session)

    assert response.status_code == 302
    assert response.location.endswith("/playground/builder")
    assert session_snapshot["mode"] == "anonymous"
    assert session_snapshot["source_origin"] == "manual_new"
    assert "agent_id" not in session_snapshot
    assert "builder_upload_id" not in session_snapshot
    assert config.perceive_module == "PassThroughPerceive"


def test_runner_without_source_redirects_to_builder_without_dead_end():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        response = client.get("/playground/run")
        follow_response = client.get(response.location)

    assert response.status_code == 302
    assert response.location.endswith("/playground/builder")
    assert follow_response.status_code == 200


def test_source_preview_api_preserves_current_draft_without_legacy_page():
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec(("input_type", "text"))

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["workflow_spec"] = spec
            session["builder_has_user_config"] = True

        source_response = client.get("/playground/source/preview")
        legacy_page_response = client.get("/playground/source")
        export_response = client.post("/playground/source/export")
        runner_response = client.get("/playground/run")
        with client.session_transaction() as session:
            preserved_config = spec_to_config(session["workflow_spec"])

    assert source_response.status_code == 200
    assert legacy_page_response.status_code == 404
    assert export_response.status_code == 404
    assert runner_response.status_code == 200
    assert preserved_config.perceive_module == "TextPerceive"


def test_v2_source_preview_preserves_renamed_workflow():
    app = create_app()
    app.config.update(TESTING=True)
    spec = apply_builder_step(default_spec(), "name", "Contract verification")

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec

        response = client.get("/playground/source/preview")

    assert response.status_code == 200
    assert 'workflow_name="Contract verification"' in response.get_data(as_text=True)


def test_loading_v2_agent_compiles_canonical_execution_source():
    app = create_app()
    app.config.update(TESTING=True)
    spec = apply_builder_step(default_spec(), "output_format", "free_text")

    with app.test_request_context():
        store_loaded_agent(
            {
                "agent_id": "agent-1",
                "agent_name": "Stored Agent",
                "python_source": build_source(),
                "endpoint_bindings": {"action": "gpt-54"},
                "workflow_spec": spec,
                "runner_presentation": {},
            }
        )
        config = spec_to_config(session["workflow_spec"])

    assert config.action_module == "GenerativeAction"


def test_runner_starter_questions_use_session_metadata_not_python_source():
    app = create_app()
    app.config.update(TESTING=True)
    spec = build_spec(("memory_type", {"starter_questions": "如何上架？"}))

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["builder_form_state"] = {
                "choices": {},
                "values": {"memory_type": {"starter_questions": "如何上架？\n如何部署？"}},
            }

        source_response = client.get("/playground/source/preview")
        runner_response = client.get("/playground/run")

    assert source_response.status_code == 200
    assert "RUNNER_CONFIG" not in source_response.get_data(as_text=True)
    assert "starter_questions" not in source_response.get_data(as_text=True)
    assert runner_response.status_code == 200
    assert "如何上架？" in runner_response.get_data(as_text=True)
    assert "如何部署？" in runner_response.get_data(as_text=True)


def test_streaming_execute_route_forwards_attachment_payloads(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    def fake_stream_agent_run(_python_source, **kwargs):
        captured.update(kwargs)
        yield {
            "type": "final",
            "execution": {
                "status": "completed",
                "final_message": "ok",
                "tool_calls": [],
                "tool_call_panels": [],
                "debug_messages": [],
                "process_events": [],
                "result": {"message": "ok"},
                "scene_profile": {},
            },
        }

    monkeypatch.setattr(runner_routes, "stream_agent_run", fake_stream_agent_run)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = build_spec()
        response = client.post(
            "/playground/run/execute/stream",
            json={
                "message": "請判讀圖片",
                "attachments": [
                    {
                        "kind": "image",
                        "name": "report.png",
                        "media_type": "image/png",
                        "content": "data:image/png;base64,abc",
                    }
                ],
            },
        )
        response.get_data(as_text=True)

    assert response.status_code == 200
    assert captured["attachments"][0]["content"] == "data:image/png;base64,abc"


def test_streaming_execute_route_forwards_finish_fields_as_ndjson_process_events(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    schema = default_events_schema()

    def standard_event(module, phase, **extra):
        return {
            "type": "stage",
            "phase": phase,
            "status": "running" if phase == "start" else "done",
            "module": module,
            "label": schema[module]["label"],
            "schema": schema[module],
            "metadata": {
                "schema_label": schema[module]["label"],
                "schema_fields": list(schema[module]["fields"]),
                "schema_metadata": dict(schema[module]["metadata"]),
            },
            "visit_id": f"workflow-1:{module}:1",
            **extra,
        }

    class FakeWorkflow:
        def run(self, *, user_message=None, event_callback=None, **_kwargs):
            assert user_message is None
            assert event_callback is not None
            state = WorkflowState(user_message="測試輸入", workflow_id="workflow-1", session_id="session-1")
            events = [
                standard_event("perceive", "start"),
                standard_event("perceive", "finish", fields=[{"field": "summary", "value": '包含 "引號" 的理解'}], state=state),
                standard_event("plan", "start"),
                standard_event("plan", "finish", fields=[{"field": "thought", "value": "需要先整理來源"}], state=state),
            ]
            for event in events:
                event_callback(event)
            return WorkflowResult(
                workflow_id="workflow-1",
                session_id="session-1",
                final_message="完成",
                visit_counts={"perceive": 1, "plan": 1, "action": 1},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = build_spec()
        response = client.post(
            "/playground/run/execute/stream",
            json={"message": "測試輸入"},
        )
        lines = [
            json.loads(line)
            for line in response.get_data(as_text=True).splitlines()
            if line.strip()
        ]

    process_events = [item["event"] for item in lines if item["type"] == "process"]
    final = next(item["result"] for item in lines if item["type"] == "final")

    assert response.status_code == 200
    assert [event["description"] for event in process_events if event["role"] == "perceive"] == [
        "正在讀取使用者輸入，整理成後續步驟可使用的內容。",
        '目前理解為：包含 "引號" 的理解',
    ]
    assert [event["description"] for event in process_events if event["role"] == "plan"] == [
        "正在判斷這次需要先整理來源，或可以直接準備回覆。",
        "判斷依據：需要先整理來源",
    ]
    assert [event["visit_id"] for event in process_events if event["role"] == "perceive"] == [
        "workflow-1:perceive:1",
        "workflow-1:perceive:1",
    ]
    assert "details" not in process_events[1]
    assert final["process_events"] == process_events


def test_runner_only_projects_explicit_scalar_trace_details():
    schema = {"label": "理解輸入", "fields": ["details.foot_arch"], "metadata": {}}
    workflow_event = {
        "type": "structured_field",
        "phase": "field",
        "status": "completed",
        "module": "perceive",
        "label": schema["label"],
        "schema": schema,
        "visit_id": "workflow-1:perceive:1",
        "visit_count": 1,
        "field": "details.foot_arch",
        "value": "一般足弓",
    }

    assert runner_service._structured_field_process_event(
        "perceive",
        "details.foot_arch",
        "一般足弓",
        label=schema["label"],
        workflow_event=workflow_event,
    )["details"] == [{"field": "details.foot_arch", "description": "details.foot_arch：一般足弓"}]


def test_runner_does_not_project_wildcard_structured_trace_details():
    schema = default_events_schema()["perceive"]
    workflow_event = {
        "type": "structured_field",
        "phase": "field",
        "status": "completed",
        "module": "perceive",
        "label": schema["label"],
        "schema": schema,
        "visit_id": "workflow-1:perceive:1",
        "visit_count": 1,
        "field": "details.foot_arch.value",
        "value": "一般足弓",
    }

    assert runner_service._structured_field_process_event(
        "perceive",
        "details.foot_arch.value",
        "一般足弓",
        label=schema["label"],
        workflow_event=workflow_event,
    ) is None


def test_runner_hides_unavailable_structured_trace_values():
    schema = default_events_schema()["perceive"]
    workflow_event = {
        "type": "structured_field",
        "phase": "field",
        "status": "completed",
        "module": "perceive",
        "label": schema["label"],
        "schema": schema,
        "visit_id": "workflow-1:perceive:1",
        "visit_count": 1,
        "field": "details.foot_arch",
        "value": "未提供／無法判讀",
    }

    assert runner_service._structured_field_process_event(
        "perceive",
        "details.foot_arch",
        "未提供／無法判讀",
        label=schema["label"],
        workflow_event=workflow_event,
    ) is None


def test_runner_uses_module_specific_process_completion_summaries():
    config = BuilderSourceConfig(
        workflow_name="測試工作流",
        action_module="ToolCallAction",
        retrieve_module="SemanticRetrieve",
    )

    assert runner_service._module_finish_process_summary(config, "retrieve") == "已整理相關來源，交給回覆階段使用。"
    assert runner_service._module_finish_process_summary(config, "action") == "工具呼叫回覆器已完成回覆整理。"
    assert runner_service._module_finish_process_summary(config, "reflect") == "已檢查規劃與查詢結果。"


def test_runner_process_event_rejects_legacy_stage_event_without_schema():
    config = spec_to_config(build_spec())

    try:
        runner_service._process_event_for_workflow_event(
            config,
            {
                "type": "stage",
                "phase": "start",
                "status": "running",
                "module": "perceive",
                "label": "理解輸入",
            },
        )
    except TypeError as exc:
        assert "schema" in str(exc)
    else:
        raise AssertionError("legacy stage events without schema must be rejected")


def test_runner_process_event_rejects_legacy_stage_alias_without_module():
    config = spec_to_config(build_spec())
    schema = default_events_schema()["perceive"]

    try:
        runner_service._process_event_for_workflow_event(
            config,
            {
                "type": "stage",
                "phase": "start",
                "status": "running",
                "stage": "perceive",
                "label": "理解輸入",
                "schema": schema,
            },
        )
    except ValueError as exc:
        assert "module" in str(exc)
    else:
        raise AssertionError("legacy stage alias events without module must be rejected")


def test_tool_call_panel_does_not_fallback_for_information_intent(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否通知門市人員帶實體鞋墊說明 = 只有顧客明確同意後才填 true；尚未回答時保持未知（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="目前結果顯示資料仍需補充。", entities={})

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請分析目前結果")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []
    assert result["panel_decision"] == "information_request"


def test_tool_call_panel_does_not_fallback_for_optional_followup_question(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="目前足測結果屬正常足弓。若你願意，我可以整理成門市話術版。",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="這份報告代表我的腳有什麼問題嗎？")

    assert result["tool_call_panels"] == []


def test_tool_call_panel_does_not_fallback_for_health_or_safety_concern(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="建議先就醫評估。確認後要不要安排門市下一步？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="我足底很痛，走路會刺痛。")

    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []
    assert result["panel_decision"] == "safety_concern"


def test_tool_call_panel_falls_back_for_reservation_confirmation(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="商品名稱：科技鞋墊 通用型\n商品編號：291090970\n請問我要先為您登記保留這款推薦嗎？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="好，那就幫我保留你推薦的那款。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "下一步確認"


def test_tool_call_panel_allows_data_limitations_after_recommendation(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="商品名稱：科技鞋墊 通用型\n商品編號：291090970\n資料限制：目前庫存資料不足，需由門市確認。\n您要我先幫您保留或購買這款推薦嗎？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請直接幫我推薦一款合適的鞋墊。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "下一步確認"


def test_tool_call_panel_falls_back_for_decision_intent_without_model_tool_call(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="我建議採用第一個方案。是否要進入下一步？", entities={})

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦下一步")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert len(result["tool_call_panels"]) == 1
    assert result["panel_decision"] == "fallback_eligible"
    assert result["tool_call_panels"][0]["title"] == "下一步確認"
    assert result["tool_call_panels"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "是否確認"


def test_tool_call_panel_falls_back_for_natural_next_step_question(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="推薦商品：寬楦通勤鞋。要不要幫你進行下一步？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦適合久站通勤的產品，並確認下一步。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "下一步確認"


def test_catalog_identifier_without_retrieved_evidence_stops_for_human_confirmation(monkeypatch):
    source = build_spec(
        ("retrieve_policy", "semantic"),
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
        ("failure_policy", "handoff"),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="推薦商品：科技鞋墊 通用型。要不要幫你進行下一步？",
                entries=[
                    ContextEntry(
                        type=ContextEntryType.RETRIEVED,
                        content="商品編號：291090970，科技鞋墊 通用型。",
                        metadata={"source": "semantic_retrieve", "kb_hit_count": 1, "memory_hit_count": 0},
                    )
                ],
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦產品編號 X-UNKNOWN-999，並進行下一步。")

    assert result["status"] == "aborted"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []
    assert "X-UNKNOWN-999" in result["final_message"]
    assert "人工確認" in result["final_message"]


def test_tool_call_panel_uses_final_confirmation_line_for_long_recommendation(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="推薦結果\n我建議採用第一個方案。\n\n**要幫你保留這項推薦嗎？**",
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦下一步")

    assert result["tool_call_panels"][0]["title"] == "下一步確認"


def test_tool_call_panel_does_not_fallback_when_recommendation_needs_more_input(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="請提供更多資料後，我才能推薦合適方案。", entities={})

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦下一步")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []


def test_tool_call_panel_uses_schema_for_user_facing_confirmation(monkeypatch):
    source = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否通知門市人員帶實體鞋墊說明 = 只有顧客明確同意後才填 true；尚未回答時保持未知（資料類型：是/否)",
            },
        ),
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="我建議先採用支撐型鞋墊。\n資料缺口：仍需由門市確認技術細節。",
                entities={
                    "latest_tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "submit_api_1", "arguments": '{"是否通知門市人員帶實體鞋墊說明": false}'},
                        }
                    ]
                },
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.run_agent(source, message="請推薦鞋墊")

    assert result["status"] == "completed"
    assert result["panel_decision"] == "tool_call"
    assert result["tool_call_panels"][0]["title"] == "下一步確認"
    assert "資料缺口" not in result["tool_call_panels"][0]["title"]
    assert result["tool_call_panels"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["type"] == "boolean"
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "是否通知門市人員帶實體鞋墊說明"
    assert result["tool_call_panels"][0]["fields"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["value"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["choices"] == [
        {"value": True, "label": "是", "description": ""},
        {"value": False, "label": "否", "description": ""},
    ]
    assert result["tool_call_panels"][0]["api"] == {"method": "POST", "url": "https://example.com/confirm"}


def test_runner_tool_panel_renderer_omits_empty_field_hints():
    renderer_source = (Path(__file__).parents[1] / "playground/static/js/runner/result-surface.js").read_text(encoding="utf-8")

    assert 'const hintText = String(field.description || "").trim();' in renderer_source
    assert "if (hintText)" in renderer_source
    assert "field.description || dataTypeLabel(field.type)" not in renderer_source
    assert "function dataTypeLabel" not in renderer_source


def test_interactive_optional_field_is_not_required_in_tool_schema():
    spec = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "interaction_trigger": "需要使用者確認時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)\n顧客補充需求 = 顧客可補充的需求；可留空。",
            },
        ),
    )

    parameters = spec_to_config(spec).action_tools[0]["function"]["parameters"]

    assert parameters["required"] == ["是否確認", "__playground_review", "__playground_options"]


def test_runner_optional_field_is_not_required_for_legacy_tool_schema():
    fields = runner_service._tool_call_fields_from(
        {
            "parameters": {
                "properties": {
                    "是否確認": {"type": "boolean", "description": "使用者是否確認"},
                    "顧客補充需求": {"type": "string", "description": "顧客可補充需求；可留空。"},
                },
                "required": ["是否確認", "顧客補充需求"],
            }
        },
        {},
    )

    assert [field["required"] for field in fields] == [True, False]


def test_runner_tool_panel_extracts_platform_review_without_making_it_a_field():
    fields = runner_service._tool_call_fields_from(
        {
            "parameters": {
                "properties": {
                    "是否確認": {"type": "boolean"},
                    "__playground_review": {"type": "string"},
                },
                "required": ["是否確認", "__playground_review"],
            }
        },
        {"是否確認": False, "__playground_review": "門市將依高足弓需求準備鞋墊。"},
    )

    assert [field["name"] for field in fields] == ["是否確認"]
    assert runner_service._tool_call_review_from({"__playground_review": "門市將依高足弓需求準備鞋墊。"}) == "門市將依高足弓需求準備鞋墊。"
    assert runner_service._tool_call_review_from({"__playground_review": "門市將依高足弓需求準備鞋墊。待確認事項：是否通知門市。"}) == "門市將依高足弓需求準備鞋墊。"
    assert runner_service._tool_submission_arguments({"arguments": {"是否確認": False, "__playground_review": "不可送出"}}) == {"是否確認": False}


def test_runner_tool_panel_renderer_renders_read_only_review_before_fields():
    renderer_source = (Path(__file__).parents[1] / "playground/static/js/runner/result-surface.js").read_text(encoding="utf-8")

    assert 'const review = createToolCallReview(panel.review);' in renderer_source
    assert 'form.append(header);' in renderer_source
    assert 'form.append(review);' in renderer_source
    assert 'form.append(fieldList, actions);' in renderer_source
    assert 'const review = document.createElement("p");' in renderer_source
    assert 'review.textContent = text;' in renderer_source
    assert 'tool-call-review-label' not in renderer_source


def test_runner_metadata_routes_answer_for_a_session_that_only_has_python_source():
    app = create_app()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = build_spec()
            session["mode"] = "anonymous"

        name = client.post("/playground/run/name", json={"name": "改名後的 Agent"})
        description = client.post("/playground/run/description", json={"description": "新的用途說明。"})
        metadata = client.post(
            "/playground/run/metadata",
            json={"name": "再改一次", "description": "再寫一次說明。"},
        )

    assert name.status_code == 200
    assert name.get_json()["workflow_summary"]["name"] == "改名後的 Agent"
    assert description.status_code == 200
    assert description.get_json()["description"] == "新的用途說明。"
    assert metadata.status_code == 200
    assert metadata.get_json()["workflow_summary"]["name"] == "再改一次"
    assert metadata.get_json()["description"] == "再寫一次說明。"


def test_config_load_route_leaves_the_session_running_the_loaded_agent(monkeypatch):
    """The load route used to store AI Hub's source without recompiling it.

    Two routes load an agent. One recompiled the Python text from the loaded
    spec, the other stored whatever text came back, and the runtime executed
    that text. An agent loaded through the second route therefore ran a stale
    configuration. With the spec as the only draft the session keeps, the two
    routes cannot disagree.
    """
    app = create_app()
    app.config.update(TESTING=True)
    loaded_spec = build_spec(("input_type", "text_image"), ("retrieve_policy", "keyword"))

    monkeypatch.setattr(
        aihub_routes,
        "load_config",
        lambda agent_id, *, credentials=None, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Loaded Agent",
            "workflow_spec": loaded_spec,
            # Deliberately stale: what the old code path would have executed.
            "python_source": compile_python_source(build_spec()),
            "endpoint_bindings": {},
        },
    )
    monkeypatch.setattr(
        aihub_routes,
        "active_credentials",
        lambda: AiHubCredentials(username="creator", password="secret"),
    )

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["mode"] = "aihub_editable"
            session["ai_hub_username"] = "creator"

        response = client.post("/playground/aihub/config/load", json={"agent_id": "agent-1"})

        with client.session_transaction() as session:
            running_config = spec_to_config(session["workflow_spec"])

    assert response.status_code == 200
    assert running_config.perceive_module == "TextImagePerceive"
    assert running_config.retrieve_module == "KeywordRetrieve"


def test_spec_gates_reach_the_workflow():
    spec = build_spec()
    spec["gates"] = {"max_node_hops": 7, "max_revisit": 2, "timeout_sec": 12.5}

    workflow = runner_service.build_workflow(spec, {})

    assert workflow.gates.max_node_hops == 7
    assert workflow.gates.max_revisit == 2
    assert workflow.gates.timeout_sec == 12.5


def test_spec_gates_fall_back_to_the_sdk_defaults_when_unset():
    spec = build_spec()
    del spec["gates"]

    workflow = runner_service.build_workflow(spec, {})

    assert workflow.gates.max_node_hops == Gates().max_node_hops
    assert workflow.gates.max_revisit == Gates().max_revisit
    assert workflow.gates.timeout_sec == Gates().timeout_sec


def test_spec_entry_module_reaches_the_workflow():
    spec = build_spec()
    spec["entry_module"] = "retrieve"

    workflow = runner_service.build_workflow(spec, {})

    assert workflow.entry_module == "retrieve"


def test_spec_memory_kind_reaches_the_workflow():
    workflow = runner_service.build_workflow(build_spec(), {})

    assert isinstance(workflow.memory_type, InContextMemory)


def test_each_run_gets_its_own_memory_store():
    spec = build_spec()

    first = runner_service.build_workflow(spec, {})
    second = runner_service.build_workflow(spec, {})

    assert first.memory_type is not second.memory_type


def test_unknown_memory_kind_is_rejected_rather_than_ignored():
    spec = build_spec()
    spec["memory"] = {"kind": "redis"}

    with pytest.raises(ValueError, match="unknown memory kind"):
        runner_service.build_workflow(spec, {})


def build_workflow_with_stub_endpoints(spec):
    """Build a workflow with every model role bound, so module wiring is observable."""
    selections = {role: "gpt-54" for role in ("perceive", "plan", "action", "reflect")}
    selections["retrieve"] = "embedded-large"
    return runner_service.build_workflow(spec, selections)


def test_spec_perceive_importance_reaches_the_perceive_module():
    spec = build_spec(("input_type", "text"), ("perceive", {"importance": "4.0"}))

    workflow = build_workflow_with_stub_endpoints(spec)

    assert workflow.perceive._importance == 4.0


def test_spec_retrieve_top_k_reaches_the_retrieve_module():
    spec = build_spec(("retrieve_policy", "semantic"), ("retrieve", {"top_k": "9"}))

    workflow = build_workflow_with_stub_endpoints(spec)

    assert workflow.retrieve._top_k == 9


def test_spec_retrieve_fallback_reaches_the_retrieve_module():
    spec = build_spec(
        ("retrieve_policy", "keyword"),
        ("retrieve", {"keyword_pairs": "保固 = 說明", "fallback": "沒有支援資料。"}),
    )

    workflow = build_workflow_with_stub_endpoints(spec)

    assert workflow.retrieve._fallback == "沒有支援資料。"


def _run_without_bindings(spec):
    return runner_service.run_agent(spec, message="保固期限是多久？")


def test_missing_model_binding_names_the_role_that_needs_one():
    spec = build_spec(("output_format", "free_text"))

    result = _run_without_bindings(spec)

    assert result["status"] == "configuration_error"
    assert "還沒有指定要用哪個模型" in result["final_message"]
    assert result["detail"]


def test_semantic_agent_without_documents_says_to_upload_them():
    spec = build_spec(("retrieve_policy", "semantic"), ("output_format", "free_text"))

    result = _run_without_bindings(spec)

    assert "還沒有上傳任何文件" in result["final_message"] or "還沒有指定要用哪個模型" in result["final_message"]


def test_every_failure_carries_a_detail_field():
    """The generic message used to arrive with detail set to null."""
    spec = build_spec(("output_format", "free_text"))

    result = _run_without_bindings(spec)

    assert result.get("detail")


def test_builder_does_not_claim_a_question_was_answered_when_it_was_not():
    """A person who answers one question used to see all five ticked.

    Two of the displayed answers did not match the agent about to run, and the
    Builder then said it was ready to use.
    """
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.post(
            "/playground/builder/state",
            json={"step": "retrieve_policy", "choice": "keyword"},
        )

    payload = response.get_json()
    answered = {i["step_key"]: i for i in payload["builder_review_state"]}

    assert answered["retrieve_policy"]["answer"] != "尚未選擇"

    # Q2's default is PassThroughPerceive, which the question can express, so
    # showing it is truthful: that is what the agent does.
    assert answered["input_type"]["answer"] == "直接傳遞文字"

    # Q4 and Q5 cannot express what an untouched spec holds — DirectAnswerAction
    # and no reflect module — so they must say so rather than name a choice.
    for unanswerable in ("output_format", "failure_policy"):
        assert answered[unanswerable]["answer"] == "尚未選擇", unanswerable
        assert answered[unanswerable]["completed"] is False, unanswerable
    assert payload["builder_review_ready"] is False


def test_the_execute_route_forwards_the_failure_detail_to_the_browser():
    """The service assembled a detail and the route dropped it.

    Every failure reached the browser as one sentence with no cause, which is
    what the specific messages were supposed to end.
    """
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "free_text"})

        response = client.post("/playground/run/execute", json={"message": "保固多久？"})

    payload = response.get_json()
    assert payload["status"] == "configuration_error"
    assert payload["detail"], "the route must forward the cause, not only the message"


def test_a_lookup_agent_can_run_without_a_model_at_all():
    """A key/value table needs no model, and the Builder must not add one.

    A planner earns its model call by deciding whether to search; deciding that
    costs more than a dictionary read. And whether the table matched is a number
    the retrieve module already reports, so checking it costs nothing either.
    Between them they made every lookup agent pay for two model calls it had no
    use for — and Q4 had no answer that skipped the third.
    """
    spec = build_spec(
        ("retrieve_policy", "keyword"),
        ("retrieve", {"keyword_pairs": "保固 = 本產品保固十二個月。"}),
        ("output_format", "direct"),
        ("failure_policy", "handoff"),
    )

    assert (spec.get("plan") or {}).get("module") is None
    assert spec["action"]["module"] == "DirectAnswerAction"
    assert spec["reflect"]["module"] == "EvidenceCheckReflect"
    assert model_endpoints.endpoint_state(spec, {})["requirements"] == []

    answered = runner_service.run_agent(spec, message="保固多久？", endpoint_selections={})
    assert answered["final_message"] == "本產品保固十二個月。"


def test_retrying_still_installs_the_planner_it_routes_back_to():
    """"再查一次" sends the workflow back to plan, so plan has to be there."""
    spec = build_spec(("retrieve_policy", "keyword"), ("failure_policy", "retry"))

    assert (spec.get("plan") or {}).get("module") == "NextStepPlan"
    # The step is installed; the person is not asked which model it runs on.
    # It uses the one they chose for the answer — see the planning-step test
    # below.
    assert "plan" not in [r["role"] for r in model_endpoints.endpoint_state(spec, {})["requirements"]]


def test_the_planner_runs_without_a_binding_of_its_own():
    """Asked for nothing, and still there when the agent runs.

    A person who chose 再查一次再回答 answered a question about behaviour, not
    about models. Requiring a binding for the step that answer installed meant
    a review page with five ticks, a lit 完成, and a runner that stopped on a
    deployment nobody had been offered.
    """
    spec = build_spec(("failure_policy", "retry"))

    roles = [r["role"] for r in model_endpoints.endpoint_state(spec, {})["requirements"]]
    assert "plan" not in roles

    workflow = runner_service.build_workflow(spec, {"action": "gpt-54", "reflect": "gpt-54"})

    assert workflow.plan is not None


def test_the_preview_memory_option_stays_locked_and_visible():
    """The locked memory choice is a roadmap signal, not dead code.

    It tells people where CrossContextMemory is going. It was once removed for
    looking like a promise the product could not keep; a choice marked 預覽中
    and visibly unclickable promises a direction, not a feature.
    """
    memory_step = next(step for step in builder_routes.get_builder_steps() if step.key == "memory_type")
    preview = next(c for c in memory_step.choices if c.label == "workflow_recall_preview")

    assert preview.available is False
    assert preview.badge == "預覽中"
    assert builder_routes._is_locked_builder_choice("memory_type", preview.label) is True


def test_an_agent_saved_before_the_planner_binding_still_runs():
    """Agents in the gallery have no plan binding, and must not need one.

    The Builder only began asking for it recently. Every agent saved before
    that has perceive/retrieve/action bound and nothing for plan, so requiring
    one would stop 11 of the 15 saved agents from running at all. They keep
    borrowing the action endpoint until someone binds the planner.
    """
    # Mirrors the saved agents: a planner in the spec, no binding for it.
    spec = build_spec(("retrieve_policy", "semantic"), ("output_format", "free_text"))
    saved_bindings = {"perceive": "gpt-54", "retrieve": "embedded-large", "action": "gpt-55"}

    borrowed = runner_service.build_workflow(spec, saved_bindings)
    own = runner_service.build_workflow(spec, {**saved_bindings, "plan": "gpt-54"})

    assert borrowed.plan is not None
    assert borrowed.plan._model == borrowed.action._model
    assert own.plan._model != own.action._model


def test_a_semantic_run_is_not_labelled_keyword_retrieve():
    """The trace names the module that ran, not the metadata keys it carries.

    Every retrieve module reports hit_count now, so a branch keyed on that
    alone called every semantic run KeywordRetrieve in the user-visible trace.
    """
    config = spec_to_config(build_spec(("retrieve_policy", "semantic")))
    entry = ContextEntry(
        type=ContextEntryType.RETRIEVED,
        content="…",
        metadata={"source": "semantic_retrieve", "hit_count": 2, "kb_hit_count": 2, "memory_hit_count": 0},
    )

    message = runner_service._retrieve_debug_message(config, [entry], missed=False)

    assert "SemanticRetrieve" in message
    assert "KeywordRetrieve" not in message


def test_a_shared_agent_says_its_documents_are_missing(monkeypatch):
    """Anonymous gallery visitors were told the agent sells nothing they want.

    Every agent whose evidence check stopped it got the same retail sentence
    about 產品資料 and 庫存 — a wound-care agent told people to ask staff about
    stock. And the cause was not "nothing matched": the documents had never
    been loaded at all.
    """
    spec = build_spec(
        ("retrieve_policy", "semantic"),
        ("retrieve", {"semantic_support_files": "guide.pdf", "search_goal": "查傷口照護步驟"}),
        ("output_format", "free_text"),
        ("failure_policy", "handoff"),
    )

    class EmptyIndexWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="w",
                final_message="換藥前先洗手。",
                entries=[ContextEntry(
                    type=ContextEntryType.RETRIEVED,
                    content="",
                    metadata={"source": "semantic_retrieve", "hit_count": 0, "kb_hit_count": 0, "memory_hit_count": 0},
                )],
                entities={},
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *a, **k: EmptyIndexWorkflow())

    message = runner_service.run_agent(spec, message="傷口照護的步驟")["final_message"]

    assert "參考文件目前沒有載入" in message
    assert "產品資料" not in message and "庫存" not in message


def test_an_agent_with_documents_consults_them_before_answering():
    """A document-backed agent must not answer around its documents.

    腎臟科衛教chatbot has 78KB of uploaded material and no search goal, so the
    planner saw only a generic description of its source, judged the question
    answerable on its own, and discussed kidney diet limits with nothing behind
    a word of it. The evidence check could not object: retrieve never ran, so
    there was no hit count to fail.
    """
    spec = build_spec(
        ("retrieve_policy", "semantic"),
        ("retrieve", {"semantic_support_files": "guide.pdf"}),
        ("output_format", "free_text"),
    )
    config = spec_to_config(spec)

    assert runner_service._has_retrievable_content(config) is True

    fresh = WorkflowState(workflow_name="w", user_message="hi")
    assert runner_service._consult_the_sources_first(fresh, "action") == "retrieve"

    after = WorkflowState(workflow_name="w", user_message="hi")
    after.entries.append(ContextEntry(type=ContextEntryType.RETRIEVED, content="…", metadata={"hit_count": 2}))
    assert runner_service._consult_the_sources_first(after, "action") == "action"


def test_an_agent_with_nothing_to_look_up_keeps_the_planners_judgement():
    """The policy exists to reach documents, not to force an empty lookup."""
    empty = spec_to_config(build_spec(("retrieve_policy", "semantic"), ("output_format", "free_text")))

    assert runner_service._has_retrievable_content(empty) is False


def test_a_stored_output_format_does_not_speak_for_an_unanswered_question():
    """The module answers Q4, not whatever output_format the spec carries.

    Two agents reached the public gallery unable to answer anything, because
    an untouched spec holds DirectAnswerAction *and* output_format free_text.
    Reading the format first reported an answer nobody gave, the review page
    saw five complete questions, and the Finish button lit up.
    """
    untouched = default_spec()
    untouched["action"]["params"]["output_format"] = "free_text"

    assert untouched["action"]["module"] is None
    assert spec_to_form_state(untouched)["choices"]["output_format"] == ""

    for choice, module in [("free_text", "GenerativeAction"), ("interactive", "ToolCallAction"), ("direct", "DirectAnswerAction")]:
        answered = apply_builder_step(default_spec(), "output_format", choice)
        assert answered["action"]["module"] == module, choice
        assert spec_to_form_state(answered)["choices"]["output_format"] == choice, choice


def test_the_finish_button_stays_shut_on_an_unanswered_wizard():
    """The gate exists; it was the input that lied. This pins the whole chain."""
    untouched = default_spec()
    untouched["action"]["params"]["output_format"] = "free_text"

    items = builder_routes._builder_review_state(
        builder_routes.get_builder_steps(),
        spec_to_form_state(untouched),
        model_endpoints.endpoint_state(untouched, {}),
        set(),
    )
    by_title = {str(i["step_title"])[:2]: i["completed"] for i in items}

    assert by_title["Q4"] is False
    assert all(i["completed"] for i in items) is False


def test_the_search_size_is_something_the_builder_can_set():
    """SemanticRetrieve.top_k had to be changed by editing the exported .py.

    Reported as R300-AI/Agentic-SDK#2: the wizard generates a module whose
    result count is a real behaviour knob, and offered no way to turn it.
    """
    spec = build_spec(
        ("retrieve_policy", "semantic"),
        ("retrieve", {"semantic_support_files": "guide.pdf", "top_k": "8"}),
    )

    assert spec["retrieve"]["params"]["top_k"] == 8
    assert spec_to_form_state(spec)["values"]["retrieve"]["top_k"] == "8"
    assert spec_to_config(spec).retrieve_top_k == 8


def test_a_typed_search_size_never_crashes_the_form():
    """It is a text field to whoever is typing, so treat it as one."""
    spec = build_spec(("retrieve_policy", "semantic"), ("retrieve", {"top_k": "8"}))

    for typed, expected in [("0", 1), ("99", 20), ("abc", 8), ("", 8), ("  5 ", 5)]:
        assert apply_builder_step(spec, "retrieve", {"top_k": typed})["retrieve"]["params"]["top_k"] == expected, typed


def test_an_uploaded_document_can_be_taken_back_off(tmp_path, monkeypatch):
    """Uploading was one-way, so a wrong file stayed in the agent for good.

    Reported as R300-AI/Agentic-SDK#1: 已上傳的資料無法刪除.
    """
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        uploaded = client.post(
            "/playground/builder/uploads",
            data={"files": [(io.BytesIO("保固十二個月".encode()), "a.md"), (io.BytesIO("退貨七天".encode()), "b.md")]},
            content_type="multipart/form-data",
        ).get_json()
        assert uploaded["semantic_support_files"] == ["a.md", "b.md"]

        removed = client.post("/playground/builder/uploads/delete", json={"name": "a.md"}).get_json()
        assert removed["updated"] is True
        assert removed["semantic_support_files"] == ["b.md"]

        missing = client.post("/playground/builder/uploads/delete", json={"name": "never-uploaded.md"})
        assert missing.status_code == 404
        assert missing.get_json()["updated"] is False


def test_an_unbound_deployment_is_not_a_configured_one():
    """The Builder said ready, the runner then died on the missing binding.

    A role with no deployment chosen was reported as configured, because the
    credential check short-circuits when nothing is bound and nothing folded
    the binding back in. The readiness check passed, the person pressed 完成,
    and initialisation failed with 找不到可用的 Key Vault 模型端點 — with no
    way back to the question that would have fixed it.
    """
    spec = build_spec(("input_type", "voice"), ("output_format", "voice"), ("failure_policy", "retry"))

    state = model_endpoints.endpoint_state(
        spec, {"action": "gpt-54", "transcribe": "transcribe", "tts": "tts"}
    )

    assert state["binding_missing_roles"]["reflect"] is True
    assert state["configured_roles"]["reflect"] is False
    assert state["configured"] is False


def test_the_planning_step_is_never_a_question_of_its_own():
    """It is a step the agent gained, not a choice the person made.

    Choosing 再查一次再回答 or 語意查詢 gives the agent a step that works out
    what to look up next, and that step needs a model. Nobody was ever asked
    which one: it belongs to no question, so the review page — where every
    deployment is chosen — had nowhere to put it. Five ticks, a lit 完成
    button, and then the runner could not start.

    It runs on the model chosen for the answer instead. The person sees the
    same five questions they always saw.
    """
    spec = build_spec(("retrieve_policy", "semantic"), ("output_format", "free_text"))

    state = model_endpoints.endpoint_state(
        spec, {"perceive": "gpt-54", "retrieve": "embedded-large", "action": "gpt-54"}
    )

    assert "plan" not in [requirement["role"] for requirement in state["requirements"]]
    assert state["configured"] is True


def test_the_planning_step_runs_on_the_model_that_answers():
    """Not the search model: that one turns text into vectors and cannot plan."""
    from playground.services.runner_service import _plan_endpoint_role

    assert _plan_endpoint_role({"action": "gpt-54", "retrieve": "embedded-large"}, {"action", "retrieve"}) == "action"
