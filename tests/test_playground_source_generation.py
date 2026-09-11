from agentic_sdk.core.events import default_events_schema
from playground.services.runner_service import _process_event_for_workflow_event, run_agent
from playground.services.workflow_spec import (
    apply_builder_step,
    compile_python_source,
    default_spec,
    spec_to_config,
    spec_to_form_state,
)
from support import build_source, build_spec


def test_runner_process_event_uses_workflow_stage_label():
    config = spec_to_config(build_spec())
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


def test_run_agent_streams_configured_stage_label():
    spec = build_spec(("retrieve_policy", "keyword"))
    spec["workflow_name"] = "Stage Agent"
    spec["events"] = {"retrieve": {"label": "正在查詢產品資料"}}
    spec["retrieve"]["params"]["items"] = [{"keywords": ["sdk"], "content": "SDK 支援階段提示。"}]
    # No plan module, so the agent needs no model endpoint to reach retrieve.
    spec["plan"] = default_spec()["plan"]
    events = []

    run_agent(spec, message="sdk", process_observer=events.append)

    assert any(event["role"] == "retrieve" and event["title"] == "正在查詢產品資料" for event in events)


def test_retrieve_builder_ignores_legacy_semantic_weight_fields():
    source = build_source(
        ("retrieve_policy", "semantic"),
        (
            "retrieve",
            {
                "top_k": "7",
                "similarity_weight": "0.6",
                "recency_weight": "0.2",
                "importance_weight": "0.2",
            },
        ),
    )

    assert "SemanticRetrieve(" in source
    assert "top_k=" not in source
    assert "similarity_weight" not in source
    assert "recency_weight" not in source
    assert "importance_weight" not in source


def test_starter_questions_do_not_emit_runner_config_in_python_source():
    source = build_source(("memory_type", {"starter_questions": "如何上架？"}))

    assert "RUNNER_CONFIG" not in source
    assert "starter_questions" not in source
    assert "workflow = Workflow(" in source


def test_generated_model_placeholders_are_role_neutral():
    source = build_source(("retrieve_policy", "semantic"), ("output_format", "free_text"))

    assert 'api_key="<API_KEY>"' in source
    assert 'base_url="<BASE_URL>"' in source
    assert 'model="<MODEL>"' in source
    assert 'embedding_model="<MODEL>"' in source
    assert "<ACTION_" not in source
    assert "<REFLECT_" not in source
    assert "<RETRIEVE_" not in source
    assert "<PERCEIVE_" not in source


def test_generated_text_image_source_omits_unselected_importance_preset():
    spec = build_spec(("input_type", "text_image"))
    source = compile_python_source(spec)

    assert "TextImagePerceive(" in source
    assert "importance=" not in source
    assert spec_to_config(spec).perceive_importance == 1.5


def test_generated_retrieve_source_omits_empty_default_parameters():
    keyword_source = build_source(("retrieve_policy", "keyword"))
    semantic_source = build_source(("retrieve_policy", "semantic"))

    assert "KeywordRetrieve()" in keyword_source
    assert "items=[]" not in keyword_source
    assert "SemanticRetrieve(" in semantic_source
    assert "sources=[]" not in semantic_source
    assert "retrieve_description=" not in semantic_source


def test_generated_semantic_source_preserves_original_pptx_filename():
    spec = build_spec(
        ("retrieve_policy", "semantic"),
        ("retrieve", {"semantic_support_files": "AI-Hub.pptx"}),
    )
    source = compile_python_source(spec)

    assert '"./AI-Hub.pptx"' in source
    assert spec_to_config(spec).semantic_support_files == ("AI-Hub.pptx",)


def test_generated_reflect_source_carries_no_failure_route():
    spec = build_spec(("failure_policy", "retry"))
    source = compile_python_source(spec)

    assert "PlanCheckReflect(" in source
    assert "on_failure" not in source


def test_generated_plan_source_keeps_user_configured_retrieve_description():
    source = build_source(
        ("retrieve_policy", "semantic"),
        ("retrieve", {"semantic_search_goal": "查找產品規格與限制"}),
        # retrieve_description reaches the planner, and a planner only exists
        # when the failure policy asks to re-plan.
        ("failure_policy", "retry"),
    )

    assert "retrieve_description=" in source
    assert "查找產品規格與限制" in source


def test_keyword_retrieve_builder_emits_only_keyword_items_without_retrieve_fallback():
    source = build_source(
        ("retrieve_policy", "keyword"),
        ("retrieve", {"keyword_pairs": "保固 = 提供保固期限與申請方式", "fallback": "沒有支援資料。"}),
    )
    retrieve_block = source.split("retrieve=KeywordRetrieve(", 1)[1].split("\n    ),", 1)[0]

    assert "KeywordRetrieve(" in source
    assert '"保固"' in source
    assert "fallback=" not in retrieve_block


def test_builder_form_state_roundtrips_generated_text_parameters():
    spec = build_spec(
        ("memory_type", {"starter_questions": "如何上架？"}),
        ("input_type", "text_image"),
        (
            "perceive",
            {
                "welcome_message": "請先辨識使用者要上架的模型與限制。",
                "image_instruction": "請特別判讀圖片中的欄位、流程、限制與警示訊息。",
                "intent_pairs": "目標 = 使用者想完成的上架結果",
            },
        ),
        ("retrieve_policy", "semantic"),
        (
            "retrieve",
            {
                "semantic_support_files": "AI Hub 上架教學.pptx",
                "semantic_search_goal": "查找 AI Hub 上架流程、限制與部署步驟",
            },
        ),
        ("output_format", "free_text"),
        ("action", {"response_instruction": "請用 FAE 口吻分步說明。"}),
    )
    source = compile_python_source(spec)

    state = spec_to_form_state(spec)

    assert state["choices"]["input_type"] == "text_image"
    assert state["choices"]["retrieve_policy"] == "semantic"
    assert state["values"]["perceive"]["welcome_message"] == "請先辨識使用者要上架的模型與限制。"
    assert state["values"]["perceive"]["image_instruction"] == "請特別判讀圖片中的欄位、流程、限制與警示訊息。"
    assert state["values"]["perceive"]["intent_pairs"] == "目標 = 使用者想完成的上架結果"
    assert state["values"]["retrieve"]["semantic_support_files"] == "AI Hub 上架教學.pptx"
    assert state["values"]["retrieve"]["semantic_search_goal"] == "查找 AI Hub 上架流程、限制與部署步驟"
    assert state["values"]["action"]["response_instruction"] == "請用 FAE 口吻分步說明。"


def test_interactive_action_adds_generic_intent_gate_without_polluting_form_state():
    spec = build_spec(
        ("output_format", "interactive"),
        (
            "action",
            {
                "response_instruction": "請依使用者情境回覆，必要時才請使用者確認下一步。",
                "api_contracts": "",
                "interaction_trigger": "使用者需要確認下一步時呼叫。",
                "api_method": "POST",
                "api_url": "https://example.com/confirm",
                "component_fields": "是否確認 = 使用者是否確認下一步（資料類型：是/否)",
            },
        ),
    )
    source = compile_python_source(spec)

    assert "先在內部判斷使用者這一輪的意圖類型" in source
    assert "當使用者只是詢問資訊、要求分析、要求解釋" in source
    assert "Playground 會依配置顯示互動元件並收集使用者選擇" in source
    assert "顯示互動元件並收集使用者選擇" in source
    assert "若使用者尚未回答，請先用 false 作為暫定值來顯示確認面板" not in source
    assert "tool_choice=\"auto\"" in source
    assert "使用者設定的回覆規範" in source

    config = spec_to_config(spec)
    state = spec_to_form_state(spec)

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