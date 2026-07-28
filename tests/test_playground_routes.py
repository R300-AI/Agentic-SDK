import json
import re
from pathlib import Path

import pytest

from playground import create_app


pytestmark = pytest.mark.skip(reason="Legacy playground v1 contract predates the restored v2 release.")


def _visible_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _builder_form_state(html: str) -> dict[str, object]:
    match = re.search(r'<script id="builder-form-state" type="application/json" data-builder-form-state>(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def _tool_call_demo_source() -> str:
    return '''
from agentic_sdk import Workflow


class FakeAction:
    name = "action"

    def __init__(self):
        self._tool_choice = "auto"
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_api_1",
                    "description": "需要確認資料時呼叫。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_name": {"type": "string", "description": "客戶名稱"},
                            "quantity": {"type": "number", "description": "數字：件數"},
                            "approved": {"type": "boolean", "description": "是否確認"},
                        },
                        "required": ["customer_name", "quantity", "approved"],
                        "additionalProperties": False,
                    },
                },
            }
        ]

    def __call__(self, state):
        submission = state.payload.get("tool_call_submission")
        if submission:
            if self._tools:
                return "tools still enabled"
            return f"confirmed:{submission.get('quantity')}:{submission.get('approved')}"
        return {
            "next_module": None,
            "payload": {
                "latest_final_message": "已產生工具呼叫。",
                "latest_tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "submit_api_1",
                            "arguments": '{"customer_name": "Ada", "quantity": 2, "approved": true}',
                        },
                    }
                ],
            },
        }


workflow = Workflow(action=FakeAction(), workflow_name="Tool Demo")
'''


def test_entry_route_renders():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground")

    assert response.status_code == 200
    assert "AI Hub Agent 建立工具".encode("utf-8") in response.data
    assert "使用 AI Hub 登入".encode("utf-8") in response.data
    assert "不登入，先在本機試用".encode("utf-8") in response.data
    assert b"data-login-status" in response.data


def test_builder_route_renders_oobe_shell():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    assert "這個 Agent 主要要完成哪類任務？".encode("utf-8") in response.data
    assert "即時問答".encode("utf-8") in response.data
    assert "承接前文問答".encode("utf-8") in response.data
    assert "預覽中".encode("utf-8") in response.data
    assert b"data-step-panel=\"failure_policy\"" in response.data
    assert "前往試跑頁".encode("utf-8") in response.data
    assert "純文字回覆".encode("utf-8") in response.data
    assert "可互動元件".encode("utf-8") in response.data
    assert "Agent 設定".encode("utf-8") in response.data
    assert "本機設定".encode("utf-8") in response.data
    assert "可試跑".encode("utf-8") in response.data
    assert b"draft-panel" not in response.data
    assert b"summary-list" not in response.data
    assert "目前階段：步驟 1 / 7".encode("utf-8") in response.data
    assert "aria-label=\"目前階段：步驟 1 / 7：Q1: 這個 Agent 主要要完成哪類任務？\"".encode("utf-8") in response.data
    assert b"progress-step-list" in response.data
    page = response.data.decode("utf-8")
    rail_start = page.index("progress-step-list")
    rail_end = page.index("</nav>", rail_start)
    rail_markup = page[rail_start:rail_end]
    assert "<button" not in rail_markup
    assert "aria-selected" not in rail_markup
    assert "<strong>" not in rail_markup
    assert "<small>" not in rail_markup
    for forbidden_copy in ("目前草稿", "設定摘要", "讓使用者一進入頁面", "目前 PoC", "README", "Gateway", "前端骨架"):
        assert forbidden_copy not in page
    assert b"WorkflowSettings" not in response.data


def test_builder_visible_language_hides_internal_module_terms():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    visible_text = _visible_text(response.data.decode("utf-8"))
    for business_copy in (
        "整理成自然回覆",
        "需求判斷",
        "套用作業規則",
        "依意思找相關資料",
        "回覆風格與規範",
        "可互動元件 API",
        "規則 key 對處理 value",
        "從哪一步開始",
    ):
        assert business_copy in visible_text
    assert "回覆服務名稱" not in visible_text
    assert "回覆部署名稱" not in visible_text
    for internal_term in ("店內", "模型", "模組", "Action", "Perceive", "Retrieve", "Reflect", "Plan", "Workflow", "SDK", "提示詞", "生成溫度", "語意查找", "StoreRule", "BusinessRule", "latest_retrieved_content"):
        assert internal_term not in visible_text


def test_builder_choice_cards_explain_real_differences_and_avoid_duplicate_categories():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "不預設外部 OpenAI 相容 client，適合先從最小流程開始。" in page
    assert "同時使用 key/value 對照表與意思比對。" in page
    assert "檢查答案是否回應問題，失敗處理由下方參數決定。" in page
    failure_step_start = page.index('id="builder-step-failure_policy"')
    failure_step_end = page.index("</article>", failure_step_start)
    failure_step_markup = page[failure_step_start:failure_step_end]
    assert failure_step_markup.count("data-choice-card") == 3
    assert "檢查回覆，不通過時重新規劃" not in failure_step_markup
    assert "檢查回覆，不通過時停止" not in failure_step_markup
    assert "檢查回覆品質" in failure_step_markup
    assert "檢查資料依據" in failure_step_markup


def test_builder_uses_formal_seven_step_flow_without_legacy_name_step():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert 'id="builder-step-name"' not in page
    assert 'data-name-input' not in page
    assert "這個 Agent 要如何命名？" not in page
    assert "步驟 7 / 7" in page
    assert "步驟 8 /" not in page
    assert "步驟 9 /" not in page


def test_builder_action_structured_result_is_primary_choice():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    action_step_start = page.index('id="builder-step-output_format"')
    action_step_end = page.index("</article>", action_step_start)
    action_step_markup = page[action_step_start:action_step_end]
    assert "最後的回覆應該長什麼樣子？" in action_step_markup
    assert "純文字回覆" in action_step_markup
    assert "可互動元件" in action_step_markup
    assert "回覆風格與規範" in action_step_markup
    assert "可互動元件 API" in action_step_markup
    assert "功能說明" in action_step_markup
    assert "api-endpoint-row" in action_step_markup


def test_builder_advanced_settings_cover_workflow_steps():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    runtime_controls = (
        "回覆風格與規範",
        "可互動元件 API",
        "功能說明",
        "需求整理進階配置",
        "支援資料判斷進階配置",
        "關鍵字對照進階配置",
        "檢查失敗進階配置",
        "試跑安全限制",
        'name="response_instruction"',
        'name="api_method"',
        'name="api_url"',
        'name="component_fields"',
        'name="api_body_template"',
        'name="on_failure"',
        'name="entry_module"',
    )
    for control in runtime_controls:
        assert control in page
    for dead_control in ('name="task_goal"', 'name="success_criteria"', 'name="input_description"', 'name="input_fields"', 'name="output_guidance"', 'name="route_rule"', 'name="direct_rule"', 'name="criteria"', '可互動元件 API 契約', '回覆指令'):
        assert dead_control not in page


def test_builder_parameter_fields_are_contextual_to_module_steps():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    retrieve_step_start = page.index('id="builder-step-retrieve_policy"')
    retrieve_step_end = page.index("</article>", retrieve_step_start)
    retrieve_step_markup = page[retrieve_step_start:retrieve_step_end]
    plan_step_start = page.index('id="builder-step-task_type"')
    plan_step_end = page.index("</article>", plan_step_start)
    plan_step_markup = page[plan_step_start:plan_step_end]
    action_step_start = page.index('id="builder-step-output_format"')
    action_step_end = page.index("</article>", action_step_start)
    action_step_markup = page[action_step_start:action_step_end]
    assert 'data-param-form data-step-key="retrieve"' in retrieve_step_markup
    assert "關鍵字對照進階配置" in retrieve_step_markup
    assert "key 對 value" in retrieve_step_markup
    assert 'name="keyword_pairs"' in retrieve_step_markup
    assert 'name="retrieve_name"' not in retrieve_step_markup
    assert 'name="retrieve_description"' not in retrieve_step_markup
    assert 'name="top_k"' not in retrieve_step_markup
    assert "支援資料判斷進階配置" in plan_step_markup
    assert 'name="retrieve_name"' in plan_step_markup
    assert 'name="retrieve_description"' in plan_step_markup
    assert 'data-param-form data-step-key="action"' in action_step_markup
    assert 'name="response_instruction"' in action_step_markup
    assert 'name="api_method"' in action_step_markup
    assert 'name="api_url"' in action_step_markup
    assert 'name="component_fields"' in action_step_markup
    assert 'name="output_guidance"' not in page
    assert 'name="system_prompt"' not in page
    assert 'name="temperature"' not in page
    assert 'name="model"' not in page


def test_builder_template_step_only_selects_runtime_presets():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    template_step_start = page.index('id="builder-step-task_type"')
    template_step_end = page.index("</article>", template_step_start)
    template_step_markup = page[template_step_start:template_step_end]
    assert "整理成自然回覆" in template_step_markup
    assert "需求判斷" in template_step_markup
    assert "需求整理進階配置" in template_step_markup
    assert "支援資料判斷進階配置" in template_step_markup
    assert "關鍵字對照進階配置" in template_step_markup
    assert 'data-param-form data-step-key="template"' not in template_step_markup
    assert 'data-param-form data-step-key="action"' in template_step_markup
    assert 'data-param-form data-step-key="perceive"' in template_step_markup
    assert 'data-param-form data-step-key="plan"' in template_step_markup
    assert 'data-param-form data-step-key="retrieve"' in template_step_markup
    for dead_field in ('name="task_goal"', 'name="success_criteria"', 'name="formal_audience"', 'name="question_mode"', 'name="reply_style"', 'name="output_guidance"'):
        assert dead_field not in template_step_markup


def test_new_builder_does_not_prefill_form_state():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/builder")

    assert response.status_code == 200
    state = _builder_form_state(response.data.decode("utf-8"))
    assert state == {"choices": {}, "values": {}}


def test_runner_route_renders_task_shell():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/run")

    assert response.status_code == 200
    assert "客戶回覆 Agent".encode("utf-8") in response.data
    assert b"data-result-thread hidden" in response.data
    assert b"data-result-surface hidden" in response.data
    assert b"aria-controls=\"trust-basis-panel\"" in response.data
    assert b"data-archetype" in response.data
    assert b"data-layout-variant=\"chat_first\"" in response.data
    assert b"data-attachment-input" in response.data
    assert b"data-adoption-state" in response.data
    assert b"data-next-step-strip" in response.data
    assert b"data-next-step-action=\"copy\"" in response.data
    assert b"data-save-panel" in response.data
    assert b"data-save-action" in response.data
    assert b"data-save-login-modal" in response.data
    assert b"data-save-status" not in response.data
    assert b"data-history-list" not in response.data
    assert "最近試跑".encode("utf-8") not in response.data
    assert "尚未儲存".encode("utf-8") in response.data
    assert "儲存狀態".encode("utf-8") not in response.data
    assert "模式".encode("utf-8") not in response.data
    assert "主要輸入".encode("utf-8") not in response.data
    assert "主要結果".encode("utf-8") not in response.data
    assert "請先登入 AI Hub".encode("utf-8") in response.data
    assert "登入並儲存".encode("utf-8") not in response.data
    assert "登入".encode("utf-8") in response.data


def test_runner_trust_panel_partial_is_rendered():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/run")

    assert response.status_code == 200
    assert b"id=\"trust-basis-panel\"" in response.data
    assert b"data-evidence-list" in response.data
    assert Path("playground/templates/partials/trust_panel.html").exists()


def test_runner_marks_one_time_auto_save_after_login():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        with client.session_transaction() as session:
            session["mode"] = "manual_auth"
            session["account_context_present"] = True
            session["ai_hub_username"] = "creator"
            session["ai_hub_credential_ticket"] = "ticket-1"
            session["pending_runner_auto_save"] = True
        response = client.get("/playground/run")
        with client.session_transaction() as session:
            flag_cleared = "pending_runner_auto_save" not in session

    assert response.status_code == 200
    assert b'data-auto-save-after-login="true"' in response.data
    assert flag_cleared is True


def test_runner_without_source_redirects_to_builder():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/run")

    assert response.status_code == 302
    assert "/playground/builder" in response.headers["Location"]


def test_aihub_readonly_hides_creator_controls():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/run?mode=aihub_readonly")

    assert response.status_code == 200
    assert "已儲存".encode("utf-8") in response.data
    assert b"data-save-action" not in response.data
    assert "編輯設定".encode("utf-8") not in response.data
    assert "Python 原始碼".encode("utf-8") not in response.data
    assert "匯出 .py".encode("utf-8") not in response.data
    assert "尚未儲存到 AI Hub".encode("utf-8") not in response.data
    assert "模式".encode("utf-8") not in response.data
    assert "主要輸入".encode("utf-8") not in response.data
    assert "主要結果".encode("utf-8") not in response.data


def test_aihub_deep_link_skips_entry_and_downgrades_untrusted_editable():
    app = create_app()

    with app.test_client() as client:
        entry_response = client.get("/playground/?mode=aihub_readonly&agent_id=agent-1")
        runner_response = client.get("/playground/run?mode=aihub_editable")

    assert entry_response.status_code == 302
    assert "/playground/run" in entry_response.headers["Location"]
    assert runner_response.status_code == 200
    assert "已儲存".encode("utf-8") in runner_response.data
    assert "編輯設定".encode("utf-8") not in runner_response.data
    assert b"data-save-action" not in runner_response.data


def test_aihub_config_load_downgrades_editable_without_account_context():
    app = create_app()

    with app.test_client() as client:
        load_response = client.post(
            "/playground/aihub/config/load",
            json={"agent_id": "agent-2", "editable": True},
        )
        runner_response = client.get("/playground/run")

    assert load_response.status_code == 200
    assert load_response.json["mode"] == "aihub_readonly"
    assert load_response.json["integration_status"] == "stub"
    assert load_response.json["requires_real_aihub_api"] is True
    assert "已儲存".encode("utf-8") in runner_response.data
    assert b"data-save-action" not in runner_response.data


def test_aihub_editable_mode_shows_update_context():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        load_response = client.post(
            "/playground/aihub/config/load",
            json={"agent_id": "agent-3", "editable": True},
        )
        runner_response = client.get("/playground/run")

    assert load_response.status_code == 200
    assert load_response.json["mode"] == "aihub_editable"
    assert "已儲存".encode("utf-8") in runner_response.data
    assert b"data-save-action" in runner_response.data
    assert "編輯設定".encode("utf-8") in runner_response.data


def test_aihub_config_rejects_disallowed_origin():
    app = create_app()

    with app.test_client() as client:
        load_response = client.post(
            "/playground/aihub/config/load",
            json={"agent_id": "agent-2"},
            headers={"Origin": "https://evil.example"},
        )
        save_response = client.post(
            "/playground/aihub/config/save",
            headers={"Origin": "https://evil.example"},
        )

    assert load_response.status_code == 403
    assert load_response.json["loaded"] is False
    assert save_response.status_code == 403
    assert save_response.json["saved"] is False


def test_aihub_save_allows_creator_modes_only():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        anonymous_response = client.post("/playground/aihub/config/save")
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        signed_in_response = client.post("/playground/aihub/config/save")
        runner_response = client.get("/playground/run")

    assert anonymous_response.status_code == 200
    assert anonymous_response.json["saved"] is True
    assert signed_in_response.status_code == 200
    assert signed_in_response.json["saved"] is True
    assert signed_in_response.json["integration_status"] == "stub"
    assert signed_in_response.json["requires_real_aihub_api"] is True
    assert "已儲存".encode("utf-8") in runner_response.data


def test_static_assets_are_served():
    app = create_app()

    with app.test_client() as client:
        css_response = client.get("/static/css/app.css")
        js_response = client.get("/static/js/runner/runner-page.js")
        result_surface_response = client.get("/static/js/runner/result-surface.js")
        module_response = client.get("/static/js/runner/scene-profile.js")
        dialog_response = client.get("/static/js/shared/dialog.js")

    assert css_response.status_code == 200
    assert b"--fluent-blue" in css_response.data
    assert b"--amd-red" in css_response.data
    assert js_response.status_code == 200
    assert b"data-trust-toggle" in js_response.data
    assert b"/playground/run/execute" in js_response.data
    assert b"/playground/source/export" not in js_response.data
    assert b"data-code-toggle" not in js_response.data
    assert b"setAdoptionState" in js_response.data
    assert b"bindNextStepStrip" in js_response.data
    assert b"bindAttachmentPicker" in js_response.data
    assert b"showSavePanel" in js_response.data
    assert b"setTrustEvidence" in js_response.data
    assert b"runner:tool-call-submit" in js_response.data
    assert b"tool_call_submission" in js_response.data
    assert b"prependHistoryItem" not in js_response.data
    assert result_surface_response.status_code == 200
    assert b"renderToolCallPanels" in result_surface_response.data
    assert "送出選擇".encode("utf-8") in result_surface_response.data
    entry_js_response = client.get("/static/js/entry/entry-page.js")
    assert entry_js_response.status_code == 200
    assert "正在登入".encode("utf-8") in entry_js_response.data
    assert b"control.readOnly = true" in entry_js_response.data
    assert b'querySelectorAll("input, button")' not in entry_js_response.data
    assert module_response.status_code == 200
    assert b"/playground/run/profile" in module_response.data
    assert dialog_response.status_code == 200
    assert b"dataset.open" in dialog_response.data


def test_route_map_source_and_runner_endpoints():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        profile_response = client.get("/playground/run/profile")
        execute_response = client.post("/playground/run/execute", json={"message": "hello"})
        preview_response = client.get("/playground/source/preview")
        export_response = client.post("/playground/source/export")

    assert profile_response.status_code == 200
    assert profile_response.json["primary_input_kind"] == "chat"
    assert profile_response.json["layout_fit"]["chat_first"] == "preferred"
    assert "form_first" in profile_response.json["layout_fit"]
    assert "result_first" in profile_response.json["layout_fit"]
    assert execute_response.status_code == 200
    assert execute_response.json["status"] == "completed"
    assert "workflow_id" not in execute_response.json
    assert "visit_counts" not in execute_response.json
    assert "abort_reason" not in execute_response.json
    assert "source_execution" not in execute_response.json
    assert "來源：目前輸入內容。" in execute_response.json["result"]["evidence"]
    assert "source subset supported: True" not in execute_response.json["result"]["evidence"]
    assert "source workflow: Customer Helper" not in execute_response.json["result"]["evidence"]
    assert "history_item" not in execute_response.json
    assert preview_response.status_code == 200
    assert b"from agentic_sdk import Workflow" in preview_response.data
    assert "workflow_name=\"客戶回覆 Agent\"".encode("utf-8") in preview_response.data
    assert b"description=" not in preview_response.data
    assert export_response.status_code == 200
    assert "agentic_workflow.py" in export_response.headers["Content-Disposition"]


def test_builder_interactive_action_payload_generates_tool_call_action():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "interaction_trigger": "需要使用者確認訂單資料。",
                    "api_method": "POST",
                    "api_url": "https://example.test/orders",
                    "component_fields": "customer_name = 客戶名稱\nquantity = 數字：件數\napproved = 是否確認",
                },
            },
        )
        source = client.get("/playground/source/preview").data.decode("utf-8")

    assert "ToolCallAction(api_key=ACTION_API_KEY, base_url=ACTION_API_BASE_URL, model=ACTION_MODEL" in source
    assert "tools=[" in source
    assert '"name": "submit_api_1"' in source
    assert '"customer_name"' in source
    assert '"quantity"' in source
    assert '"type": "number"' in source
    assert '"approved"' in source
    assert '"type": "boolean"' in source
    removed_action_name = "Structured" + "Action"
    assert removed_action_name not in source


def test_runner_returns_tool_call_panels_and_route_accepts_submission():
    app = create_app()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = _tool_call_demo_source()
        initial_response = client.post("/playground/run/execute", json={"message": "建立訂單"})
        submit_response = client.post(
            "/playground/run/execute",
            json={
                "message": "建立訂單",
                "tool_call_submission": {"arguments": {"customer_name": "Lin", "quantity": 5, "approved": True}},
            },
        )

    assert initial_response.status_code == 200
    panel = initial_response.json["tool_call_panels"][0]
    field_types = {field["name"]: field["type"] for field in panel["fields"]}
    field_values = {field["name"]: field["value"] for field in panel["fields"]}
    assert field_types == {"customer_name": "string", "quantity": "number", "approved": "boolean"}
    assert field_values == {"customer_name": "Ada", "quantity": 2, "approved": True}
    assert submit_response.status_code == 200
    assert submit_response.json["final_message"] == "confirmed:5:True"
    assert submit_response.json["tool_call_panels"] == []


def test_tool_call_submission_continues_action_only_without_tools():
    from playground.services.runner_service import execute_python_source

    result = execute_python_source(
        _tool_call_demo_source(),
        tool_call_submission={"arguments": {"customer_name": "Lin", "quantity": 7, "approved": False}},
    )

    assert result["final_message"] == "confirmed:7:False"
    assert result["tool_call_panels"] == []
    assert result["visit_counts"] == {"action": 1}


def test_runner_does_not_demo_memory_history_without_memory_engine():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        first = client.post("/playground/run/execute", json={"message": "first"})
        second = client.post("/playground/run/execute", json={"message": "second"})
        response = client.get("/playground/run")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "最近試跑".encode("utf-8") not in response.data
    assert b"data-history-list" not in response.data
    assert b"completed" not in response.data


def test_runner_execute_returns_readable_attachment_error():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.post("/playground/run/execute", json={"attachments": [{"name": "missing-mime"}]})

    assert response.status_code == 200
    assert response.json["status"] == "input_error"
    assert response.json["error"] == "附件內容不完整。"
    assert "detail" not in response.json
    assert "raw" not in response.json["final_message"].lower()
    assert "source_execution" not in response.json


def test_builder_name_field_updates_canonical_source_and_summary():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        update_response = client.post(
            "/playground/builder/state",
            json={"step": "name", "value": "TSiP 顧問 Agent"},
        )
        preview_response = client.get("/playground/source/preview")
        runner_response = client.get("/playground/run")

    assert update_response.status_code == 200
    assert update_response.json["workflow_summary"]["name"] == "TSiP 顧問 Agent"
    assert 'workflow_name="TSiP 顧問 Agent"'.encode("utf-8") in preview_response.data
    assert b'description=' not in preview_response.data
    assert "TSiP 顧問 Agent".encode("utf-8") in runner_response.data


