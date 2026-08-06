import pytest

from agentic_sdk.core.events import default_events_schema
from playground.services.source_builder import build_default_python_source, build_python_source_from_builder_choice, config_from_source, get_builder_form_state, get_workflow_summary
from playground.services.source_parser import parse_supported_source
from playground.services.runner_service import _process_event_for_workflow_event, execute_python_source
from playground.services.workflow_spec import apply_builder_step, compile_python_source, default_spec


def _sample_workflow_source(workflow_name: str, profile_hint: str | None = None) -> str:
    hint_line = f"# Playground profile hint: {profile_hint}\n" if profile_hint else ""
    return (
        "from agentic_sdk import Workflow\n\n"
        f"{hint_line}"
        "workflow = Workflow(\n"
        f"    workflow_name={workflow_name!r},\n"
        ")\n"
    )


def test_parse_supported_default_source_name():
    parsed = parse_supported_source(build_default_python_source())
    config = config_from_source(build_default_python_source())
    source = build_default_python_source()

    assert parsed.workflow_name == "default"
    assert parsed.supported_subset is True
    assert "WorkflowSettings" not in source
    assert "from agentic_sdk import Workflow" in source
    assert "InContextMemory" not in source
    assert "memory = InContextMemory()" not in source
    assert "memory_type=memory" not in source
    assert config.events_schema is None
    assert "events_schema=" not in source


def test_events_schema_roundtrips_from_workflow_source():
    source = """from agentic_sdk import Workflow

workflow = Workflow(
    workflow_name="Stage Agent",
    events_schema={"retrieve": {"label": "正在查詢產品資料"}},
)
"""

    config = config_from_source(source)

    assert config.events_schema == {
        "retrieve": {
            "label": "正在查詢產品資料",
            "fields": [],
            "metadata": {},
        }
    }


def test_events_schema_source_raises_for_invalid_module_key():
    source = """from agentic_sdk import Workflow

workflow = Workflow(
    workflow_name="Stage Agent",
    events_schema={"stage_labels": {"label": "Legacy"}},
)
"""

    with pytest.raises(ValueError, match="events_schema module key"):
        config_from_source(source)


def test_runner_process_event_uses_workflow_stage_label():
    config = config_from_source(build_default_python_source())
    schema = default_events_schema()["retrieve"]

    event = _process_event_for_workflow_event(
        config,
        {
            "type": "stage",
            "phase": "start",
            "status": "running",
            "module": "retrieve",
            "label": "正在查詢產品資料",
            "schema": {**schema, "label": "正在查詢產品資料"},
        },
    )

    assert event["role"] == "retrieve"
    assert event["module"] == "retrieve"
    assert event["title"] == "正在查詢產品資料"
    assert event["description"] == "正在整理這一步可用的參考內容。"
    assert event["phase"] == "start"
    assert event["status"] == "running"
    assert event["tracked_fields"] == []


def test_execute_python_source_streams_configured_stage_label():
    source = """from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, KeywordRetrieve, PassThroughPerceive

workflow = Workflow(
    workflow_name="Stage Agent",
    events_schema={"retrieve": {"label": "正在查詢產品資料"}},
    perceive=PassThroughPerceive(),
    retrieve=KeywordRetrieve(items=[{"keywords": ["sdk"], "content": "SDK 支援階段提示。"}]),
    action=DirectAnswerAction(),
)
"""
    events = []

    execute_python_source(source, message="sdk", process_observer=events.append)

    assert any(event["role"] == "retrieve" and event["title"] == "正在查詢產品資料" for event in events)


def test_parse_generated_profile_hint_for_summary():
    python_source = _sample_workflow_source("default", "Summary")
    parsed = parse_supported_source(python_source)
    summary = get_workflow_summary(python_source)

    assert parsed.profile_hint == "Summary"
    assert summary.name == "default"
    assert summary.can_roundtrip is True


def test_parse_structured_action_profile_hint():
    python_source = _sample_workflow_source("default", "Structured Result")
    parsed = parse_supported_source(python_source)
    summary = get_workflow_summary(python_source)

    assert parsed.profile_hint == "Structured Result"
    assert summary.template == "結構化結果"


def test_parse_profile_hint_templates():
    openai_source = _sample_workflow_source("default", "OpenAI Client")
    custom_source = _sample_workflow_source("default", "Custom Action")

    assert parse_supported_source(openai_source).workflow_name == "default"
    assert get_workflow_summary(openai_source).template == "模型回覆"
    assert parse_supported_source(custom_source).workflow_name == "default"
    assert get_workflow_summary(custom_source).template == "自訂處理"


def test_execute_marks_unsupported_source_without_running_arbitrary_code():
    python_source = """from agentic_sdk import Workflow

exec("raise RuntimeError('should not run')")
workflow = Workflow()
"""

    result = execute_python_source(python_source, message="hello")

    assert result["status"] == "completed"
    assert result["source_execution"]["supported_subset"] is False
    assert result["source_execution"]["workflow_name"] == "playground_preview"
    assert result["result"]["evidence"] == ["來源：目前輸入內容。", "外部資料：尚未加入。"]


def test_retrieve_builder_ignores_legacy_semantic_weight_fields():
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)
    source = build_python_source_from_builder_choice(
        "retrieve",
        {
            "top_k": "7",
            "similarity_weight": "0.6",
            "recency_weight": "0.2",
            "importance_weight": "0.2",
        },
        source,
    )

    assert "SemanticRetrieve(" in source
    assert "top_k=" not in source
    assert "similarity_weight" not in source
    assert "recency_weight" not in source
    assert "importance_weight" not in source


def test_starter_questions_do_not_emit_runner_config_in_python_source():
    source = build_python_source_from_builder_choice("memory_type", {"starter_questions": "如何上架？"}, None)

    assert "RUNNER_CONFIG" not in source
    assert "starter_questions" not in source
    assert "workflow = Workflow(" in source


def test_generated_model_placeholders_are_role_neutral():
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)
    source = build_python_source_from_builder_choice("output_format", "free_text", source)

    assert 'api_key="<API_KEY>"' in source
    assert 'base_url="<BASE_URL>"' in source
    assert 'model="<MODEL>"' in source
    assert 'embedding_model="<MODEL>"' in source
    assert "<ACTION_" not in source
    assert "<REFLECT_" not in source
    assert "<RETRIEVE_" not in source
    assert "<PERCEIVE_" not in source


def test_generated_text_image_source_omits_unselected_importance_preset():
    source = build_python_source_from_builder_choice("input_type", "text_image", None)

    assert "TextImagePerceive(" in source
    assert "importance=" not in source
    assert config_from_source(source).perceive_importance == 1.5


def test_generated_retrieve_source_omits_empty_default_parameters():
    keyword_source = build_python_source_from_builder_choice("retrieve_policy", "keyword", None)
    semantic_source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)

    assert "KeywordRetrieve()" in keyword_source
    assert "items=[]" not in keyword_source
    assert "SemanticRetrieve(" in semantic_source
    assert "sources=[]" not in semantic_source
    assert "retrieve_description=" not in semantic_source


def test_generated_reflect_source_omits_default_retry_policy_but_roundtrips():
    source = build_python_source_from_builder_choice("failure_policy", "retry", None)

    assert "ResponseCheckReflect(" in source
    assert 'on_failure="retry_plan"' not in source
    assert config_from_source(source).reflect_on_failure == "retry_plan"


def test_generated_plan_source_keeps_user_configured_retrieve_description():
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)
    source = build_python_source_from_builder_choice("retrieve", {"semantic_search_goal": "查找產品規格與限制"}, source)

    assert "retrieve_description=" in source
    assert "查找產品規格與限制" in source


def test_legacy_runner_config_still_parses_for_existing_sources():
    source = """from agentic_sdk import Workflow

RUNNER_CONFIG = {"starter_questions": ["如何上架？"]}

workflow = Workflow(
    workflow_name="Legacy Agent",
)
"""

    config = config_from_source(source)

    assert config.starter_questions == ("如何上架？",)


def test_custom_action_builder_emits_module_standard_action():
    source = _sample_workflow_source("固定格式 Agent", "Custom Action")
    source = build_python_source_from_builder_choice(
        "action",
        {
            "class_name": "SupportRule",
            "memory_key": "latest_retrieved_content",
            "fallback": "沒有可用資料。",
            "prefix": "處理結果：",
            "rule_title": "規則",
            "rule_instruction": "只回覆已知資料。",
        },
        source,
    )

    assert "from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState" in source
    assert "class SupportRule:" in source
    assert 'name = "action"' in source
    assert "def __call__(self, state: WorkflowState) -> ModuleOutput:" in source
    assert "state.lookup(\"latest_retrieved_content\")" in source
    assert 'payload={"latest_final_message": content}' in source
    assert "ContextEntry(" in source

    result = execute_python_source(source, message="請處理", process_observer=lambda _event: None)

    assert result["status"] == "completed"
    assert result["final_message"].startswith("處理結果：")
    assert result["result"]["message"] == result["final_message"]


def test_keyword_retrieve_builder_emits_only_keyword_items_without_retrieve_fallback():
    source = build_python_source_from_builder_choice(
        "retrieve",
        {"keyword_pairs": "保固 = 提供保固期限與申請方式", "fallback": "沒有支援資料。"},
        None,
    )
    retrieve_block = source.split("retrieve=KeywordRetrieve(", 1)[1].split("\n    ),", 1)[0]

    assert "KeywordRetrieve(" in source
    assert '"保固"' in source
    assert "fallback=" not in retrieve_block


def test_builder_form_state_roundtrips_generated_text_parameters():
    source = build_python_source_from_builder_choice("memory_type", {"starter_questions": "如何上架？"}, None)
    source = build_python_source_from_builder_choice("input_type", "text_image", source)
    source = build_python_source_from_builder_choice(
        "perceive",
        {
            "welcome_message": "請先辨識使用者要上架的模型與限制。",
            "image_instruction": "請特別判讀圖片中的欄位、流程、限制與警示訊息。",
            "intent_pairs": "目標 = 使用者想完成的上架結果",
        },
        source,
    )
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", source)
    source = build_python_source_from_builder_choice(
        "retrieve",
        {
            "semantic_support_files": "AI Hub 上架教學.pptx",
            "semantic_search_goal": "查找 AI Hub 上架流程、限制與部署步驟",
        },
        source,
    )
    source = build_python_source_from_builder_choice("output_format", "free_text", source)
    source = build_python_source_from_builder_choice("action", {"response_instruction": "請用 FAE 口吻分步說明。"}, source)

    state = get_builder_form_state(source)

    assert state["choices"]["input_type"] == "text_image"
    assert state["choices"]["retrieve_policy"] == "semantic"
    assert state["values"]["perceive"]["welcome_message"] == "請先辨識使用者要上架的模型與限制。"
    assert state["values"]["perceive"]["image_instruction"] == "請特別判讀圖片中的欄位、流程、限制與警示訊息。"
    assert state["values"]["perceive"]["intent_pairs"] == "目標 = 使用者想完成的上架結果"
    assert state["values"]["retrieve"]["semantic_support_files"] == "AI Hub 上架教學.pptx"
    assert state["values"]["retrieve"]["semantic_search_goal"] == "查找 AI Hub 上架流程、限制與部署步驟"
    assert state["values"]["action"]["response_instruction"] == "請用 FAE 口吻分步說明。"


def test_interactive_action_adds_generic_intent_gate_without_polluting_form_state():
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "response_instruction": "請依使用者情境回覆，必要時才請使用者確認下一步。",
            "api_contracts": "",
            "interaction_trigger": "使用者需要確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認下一步（資料類型：是/否)",
        },
        source,
    )

    assert "先在內部判斷使用者這一輪的意圖類型" in source
    assert "當使用者只是詢問資訊、要求分析、要求解釋" in source
    assert "Playground 會依配置顯示互動元件並收集使用者選擇" in source
    assert "顯示互動元件並收集使用者選擇" in source
    assert "若使用者尚未回答，請先用 false 作為暫定值來顯示確認面板" not in source
    assert "tool_choice=\"auto\"" in source
    assert "使用者設定的回覆規範" in source

    config = config_from_source(source)
    state = get_builder_form_state(source)

    assert config.action_prompt == "請依使用者情境回覆，必要時才請使用者確認下一步。"
    assert config.action_tool_choice == "auto"
    assert state["values"]["action"]["response_instruction"] == "請依使用者情境回覆，必要時才請使用者確認下一步。"


def test_v2_interactive_action_enables_tool_calling_after_builder_update():
    spec = apply_builder_step(default_spec(), "output_format", "interactive")
    spec = apply_builder_step(
        spec,
        "action",
        {
            "response_instruction": "只有明確需要門市協助時才呼叫工具。",
            "api_contracts": '[{"interaction_trigger":"顧客明確要求門市協助時呼叫。","api_method":"POST","api_url":"https://example.com/assist","component_fields":"是否協助 = 顧客同意（資料類型：是/否）"}]',
        },
    )

    assert spec["action"]["params"]["tool_choice"] == "auto"
    assert 'tool_choice="auto"' in compile_python_source(spec)