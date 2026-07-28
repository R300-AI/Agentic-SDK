import json
import ast
from io import BytesIO
import re

from playground import create_app
from playground.services.source_builder import build_default_python_source, build_python_source_from_builder_choice, get_builder_steps


_EXPORTED_MODULE_NAMES = {
    "GenerativeAction",
    "ToolCallAction",
    "DirectAnswerAction",
    "EvidenceCheckReflect",
    "ResponseCheckReflect",
    "KeywordRetrieve",
    "SemanticRetrieve",
    "PassThroughRetrieve",
    "NextStepPlan",
    "PassThroughPerceive",
    "TextPerceive",
    "TextImagePerceive",
}


def _builder_form_state(html: str) -> dict[str, object]:
    match = re.search(r'<script id="builder-form-state" type="application/json" data-builder-form-state>(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def _builder_endpoint_state(html: str) -> dict[str, object]:
    match = re.search(r'<script id="builder-endpoint-state" type="application/json" data-builder-endpoint-state>(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def _imported_module_names(python_source: str) -> set[str]:
    tree = ast.parse(python_source)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "agentic_sdk.modules":
            for alias in node.names:
                names.add(alias.name)
    return names


def _imported_module_names_in_order(python_source: str) -> list[str]:
    tree = ast.parse(python_source)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "agentic_sdk.modules":
            return [alias.name for alias in node.names]
    return []


def _used_exported_module_names(python_source: str) -> set[str]:
    tree = ast.parse(python_source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        else:
            continue
        if call_name in _EXPORTED_MODULE_NAMES:
            names.add(call_name)
    return names


def test_builder_uses_memory_step_then_configured_perceive_modes():
    steps = get_builder_steps()

    assert [step.key for step in steps] == [
        "memory_type",
        "input_type",
        "retrieve_policy",
        "output_format",
        "failure_policy",
        "readiness",
    ]
    assert [step.title for step in steps] == [
        "Q1: 這個 Agent 主要要完成哪類任務？",
        "Q2: 這個 Agent 要如何理解輸入？",
        "Q3: 回答前需要查資料嗎？",
        "Q4: 最後回覆要怎麼呈現給使用者？",
        "Q5: 當 Agent 沒把握時，你希望它怎麼做？",
        "Q6: 最後確認，準備開始使用",
    ]
    assert [choice.label for choice in steps[1].choices] == ["pass_through", "text", "text_image"]
    assert [choice.title for choice in steps[1].choices] == ["直接傳遞文字", "整理文字內容", "整理文字與圖片"]


def test_builder_page_does_not_render_legacy_task_type_step():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert 'id="builder-step-task_type"' not in page
    assert 'data-progress-step="task_type"' not in page
    assert "Q3: 收到需求後，要怎麼決定下一步？" not in page
    assert 'data-param-form data-step-key="plan"' not in page
    assert 'template-action-custom-rule-title' not in page
    assert 'reflect-retry-on-failure' not in page
    assert "目前階段：步驟 1 / 6" in page


def test_builder_step2_exposes_shared_focus_and_field_configuration():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "進階設定" in page
    assert "Agent 要優先判讀哪些重點？" in page
    assert "要擷取哪些欄位資訊？" in page
    assert "輸入你希望 Agent 讀文字時優先注意的語意重點。" not in page
    assert "輸入你希望 Agent 綜合文字與圖片時優先注意的重點，可包含文字內容、圖片內容，或兩者之間的關聯。" not in page
    assert "新增你希望 Agent 從文字內容中擷取的明確欄位。" not in page
    assert "新增你希望 Agent 從文字與圖片中擷取的明確欄位。" not in page
    assert "每列代表一項要送出的資料；欄位名稱會對應實際送出的資料名稱。" not in page
    assert 'data-visible-choices="text|text_image"' in page
    assert 'data-input-type-form' in page
    assert page.count('pair-add-icon') >= 2
    assert 'name="image_instruction"' not in page
    assert "圖片要看什麼" not in page
    assert "照片判讀重點" not in page
    assert "整理方式" not in page
    assert "之後回想優先度" not in page
    assert "JSON key" not in page
    assert "JSON 欄位" not in page
    assert "表單欄位" not in page
    assert "混合輸入" not in page


def test_builder_step1_starter_questions_roundtrip_to_runner():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post(
            "/playground/builder/state",
            json={
                "step": "memory_type",
                "value": {
                    "starter_questions": "這份內容的重點是什麼？\n下一步該怎麼做？",
                },
            },
        )
        source_page = client.get("/playground/source/preview").data.decode("utf-8")
        runner_page = client.get("/playground/run").data.decode("utf-8")
        builder_page = client.get("/playground/builder").data.decode("utf-8")

    assert "RUNNER_CONFIG" in source_page
    assert '"starter_questions": [' in source_page
    assert "下一步該怎麼做？" in source_page
    assert 'data-starter-questions' in runner_page
    assert 'data-starter-question-button' in runner_page
    assert "這份內容的重點是什麼？" in runner_page
    assert _builder_form_state(builder_page) == {"choices": {}, "values": {}}


def test_runner_uses_builder_endpoint_selections_without_runner_endpoint_controls():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text"})
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "retrieve",
                "value": {"semantic_support_files": "a.pdf", "semantic_search_goal": "退款條件"},
            },
        )
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "free_text"})
        client.post(
            "/playground/builder/endpoints",
            json={
                "selections": {
                    "perceive": "gpt-54",
                    "retrieve": "embedded",
                    "action": "gpt-54",
                }
            },
        )
        runner_page = client.get("/playground/run").data.decode("utf-8")

    assert "Hi! 訪客" in runner_page
    assert 'data-endpoint-form' not in runner_page
    assert 'data-endpoint-deploy' not in runner_page
    assert 'data-endpoint-panel' not in runner_page
    assert 'data-placeholder="可填寫這個 Agent 的用途、適用情境或回覆目標。"' in runner_page
    assert 'class="chat-intro"' not in runner_page
    assert "可開始使用" not in runner_page
    assert "輸入問題、客戶情境或參考資料。" not in runner_page
    assert "請貼上要處理的內容，我會直接在這裡回覆。" in runner_page
    assert '<span class="eyebrow">AI Hub Agent</span>' not in runner_page
    assert '<span class="eyebrow">Agentic SDK</span>' in runner_page
    assert '>workflow_name</span>' not in runner_page
    assert '>description</span>' not in runner_page
    assert 'data-placeholder="可填寫這個 Agent 的用途、適用情境或回覆目標。"' in runner_page


def test_runner_can_rename_workflow_and_export_uses_new_name():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        runner_page = client.get("/playground/run").data.decode("utf-8")
        response = client.post("/playground/run/name", json={"name": "售後支援 Agent"})
        renamed_runner_page = client.get("/playground/run").data.decode("utf-8")
        preview_source = client.get("/playground/source/preview").data.decode("utf-8")
        exported_source = client.post("/playground/source/export").data.decode("utf-8")

    assert 'data-side-workflow-title-display' in runner_page
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["workflow_summary"]["name"] == "售後支援 Agent"
    assert "售後支援 Agent" in renamed_runner_page
    assert '<h1 id="runner-title"' not in renamed_runner_page
    assert 'workflow_name="售後支援 Agent"' in preview_source
    assert 'workflow_name="售後支援 Agent"' in exported_source
    assert 'description=' not in preview_source
    assert 'description=' not in exported_source


def test_runner_greeting_uses_logged_in_username():
    app = create_app()

    with app.test_client() as client:
        with client.session_transaction() as session_state:
            session_state["mode"] = "manual_auth"
            session_state["ai_hub_username"] = "alice@example.com"
            session_state["python_source"] = build_default_python_source()
            session_state["source_origin"] = "manual_new"
        runner_page = client.get("/playground/run").data.decode("utf-8")

    assert "Hi! alice@example.com" in runner_page


def test_runner_can_update_workflow_description_and_export_uses_new_value():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        response = client.post("/playground/run/description", json={"description": "處理客戶回覆情境，並維持既定品牌語氣。"})
        runner_page = client.get("/playground/run").data.decode("utf-8")
        preview_source = client.get("/playground/source/preview").data.decode("utf-8")
        exported_source = client.post("/playground/source/export").data.decode("utf-8")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["description"] == "處理客戶回覆情境，並維持既定品牌語氣。"
    assert "處理客戶回覆情境，並維持既定品牌語氣。" in runner_page
    assert 'description="處理客戶回覆情境，並維持既定品牌語氣。"' in preview_source
    assert 'description="處理客戶回覆情境，並維持既定品牌語氣。"' in exported_source
    assert '"goal": "處理客戶回覆情境，並維持既定品牌語氣。"' not in preview_source
    assert '"goal": "處理客戶回覆情境，並維持既定品牌語氣。"' not in exported_source


def test_runner_can_clear_workflow_description_and_source_omits_description_argument():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/run/description", json={"description": "先填一段說明"})
        response = client.post("/playground/run/description", json={"description": "   "})
        runner_page = client.get("/playground/run").data.decode("utf-8")
        preview_source = client.get("/playground/source/preview").data.decode("utf-8")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["description"] == ""
    assert 'data-placeholder="可填寫這個 Agent 的用途、適用情境或回覆目標。"' in runner_page
    assert 'description=' not in preview_source


def test_legacy_runner_placeholder_description_is_treated_as_empty():
    app = create_app()
    legacy_source = build_default_python_source().replace(
        'workflow_name="客戶回覆 Agent",',
        'workflow_name="客戶回覆 Agent",\n    description="模型部署與端點選擇已在建立流程完成；這裡只保留試跑與結果檢視。",',
    )

    with app.test_client() as client:
        with client.session_transaction() as session_state:
            session_state["mode"] = "manual_anonymous"
            session_state["python_source"] = legacy_source
            session_state["source_origin"] = "manual_new"
        runner_page = client.get("/playground/run").data.decode("utf-8")
        preview_source = client.get("/playground/source/preview").data.decode("utf-8")

    assert "模型部署與端點選擇已在建立流程完成；這裡只保留試跑與結果檢視。" not in runner_page
    assert 'data-placeholder="可填寫這個 Agent 的用途、適用情境或回覆目標。"' in runner_page
    assert "模型部署與端點選擇已在建立流程完成；這裡只保留試跑與結果檢視。" not in preview_source


def test_builder_step2_choices_update_perceive_source():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "perceive",
                "value": {
                    "welcome_message": "先判讀需求、限制條件與期望結果。",
                    "intent_pairs": "日期 = 文字中提到的事件時間",
                },
            },
        )
        text_source = client.get("/playground/source/preview").data.decode("utf-8")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text_image"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "perceive",
                "value": {
                    "welcome_message": "請綜合文字與圖片判讀需求、異常處與是否一致。",
                    "intent_pairs": "產品型號 = 可從文字描述或圖片標示辨識的型號資訊",
                },
            },
        )
        image_source = client.get("/playground/source/preview").data.decode("utf-8")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "pass_through"})
        pass_source = client.get("/playground/source/preview").data.decode("utf-8")

    assert "TextPerceive(" in text_source
    assert "api_key=" in text_source
    assert "base_url=" in text_source
    assert "model=" in text_source
    assert 'welcome_message="先判讀需求、限制條件與期望結果。"' in text_source
    assert "日期" in text_source
    assert "TextImagePerceive(" in image_source
    assert 'welcome_message="請綜合文字與圖片判讀需求、異常處與是否一致。"' in image_source
    assert "產品型號" in image_source
    assert "image_instruction=" not in image_source
    assert "PassThroughPerceive()" in pass_source
    assert "TextPerceive(" not in pass_source
    assert "TextImagePerceive(" not in pass_source


def test_builder_step4_free_text_choice_does_not_emit_builder_scaffold_prompt_by_default():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "free_text"})
        source_page = client.post("/playground/source/export").data.decode("utf-8")

    assert "GenerativeAction(" in source_page
    assert "system_prompt=" not in source_page
    assert "請依使用者需求自然回覆" not in source_page
    assert "回覆風格與規範：" not in source_page


def test_builder_step4_free_text_uses_only_user_response_instruction_in_system_prompt():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "free_text"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "response_instruction": "請用台灣繁體中文，先給結論，再列三個重點。",
                },
            },
        )
        source_page = client.post("/playground/source/export").data.decode("utf-8")

    assert 'system_prompt="請用台灣繁體中文，先給結論，再列三個重點。"' in source_page
    assert "請依使用者需求自然回覆" not in source_page
    assert "回覆風格與規範：" not in source_page


def test_builder_step4_interactive_without_response_instruction_does_not_emit_builder_scaffold_prompt():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "interactive"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "api_contracts": '[{"interaction_trigger":"確認預約資料","api_method":"POST","api_url":"https://example.test/bookings","component_fields":"customer_name = 客戶姓名"}]',
                },
            },
        )
        source_page = client.post("/playground/source/export").data.decode("utf-8")

    assert "ToolCallAction(" in source_page
    assert "tools=[" in source_page
    assert "system_prompt=" not in source_page
    assert "請同時支援純文字回覆與 OpenAI tool calling" not in source_page
    assert "互動輸出請使用 OpenAI tools/function calling" not in source_page


def test_builder_step3_only_exposes_keyword_and_semantic_retrieve_paths():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert 'data-visible-choices="semantic"' in page
    assert 'data-visible-choices="keyword"' in page
    assert "沒有資料時的處理" not in page
    assert 'name="fallback"' not in page
    assert "hybrid_later" not in page
    assert "混合查詢" not in page
    assert "要上傳哪些支援文件？" in page
    assert 'name="semantic_support_files"' in page
    assert 'type="file"' in page
    assert 'data-semantic-upload-input' in page
    assert 'data-semantic-upload-list' in page
    assert 'data-semantic-upload-progress' in page
    assert "這批資料要讓 Agent 查什麼？" in page
    assert 'name="semantic_search_goal"' in page
    assert "要對照哪些關鍵字內容？" in page
    assert 'aria-label="新增欄位"' in page


def test_builder_step5_exposes_two_uncertainty_handling_choices():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "當 Agent 沒把握時，你希望它怎麼做？" in page
    assert "再查一次再回答" in page
    assert "先停下來，交給人確認" in page
    assert "先追問" not in page
    assert "重新查資料" not in page
    assert "保守回答" not in page
    assert "轉人工" not in page


def test_builder_step6_exposes_review_checklist_and_model_endpoint_section():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "Q6: 最後確認，準備開始使用" in page
    assert 'data-builder-review-checklist' in page
    assert 'data-review-step="memory_type"' in page
    assert 'data-review-step="failure_policy"' in page
    assert 'class="builder-review-header"' in page
    assert 'data-review-answer' in page
    assert 'data-review-endpoint-body' in page
    assert 'data-builder-endpoint-state' in page
    assert "試跑安全限制" not in page
    assert 'name="entry_module"' not in page
    assert 'name="max_node_hops"' not in page
    assert 'name="max_revisit"' not in page
    assert 'name="timeout_sec"' not in page


def test_builder_state_rejects_legacy_step_keys():
    app = create_app()

    with app.test_client() as client:
        response = client.post("/playground/builder/state", json={"step": "template", "choice": "Recommendation"})

    assert response.status_code == 400
    assert response.get_json() == {"updated": False, "error": "Unsupported builder step."}


def test_builder_step3_semantic_questions_roundtrip_to_source_and_form_state():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "retrieve",
                "value": {
                    "semantic_support_files": "產品手冊.pdf\n退款政策.docx",
                    "semantic_search_goal": "退款條件與保固限制",
                },
            },
        )
        source_page = client.get("/playground/source/preview").data.decode("utf-8")
        builder_page = client.get("/playground/builder").data.decode("utf-8")

    state = _builder_form_state(builder_page)
    assert state == {"choices": {}, "values": {}}
    assert 'RETRIEVE_CONFIG = {' in source_page
    assert '"semantic_support_files": [' in source_page
    assert '"產品手冊.pdf"' in source_page
    assert '"退款政策.docx"' in source_page
    assert '"semantic_search_goal": "退款條件與保固限制"' in source_page
    assert 'SemanticRetrieve(' in source_page
    assert 'embedding_model=' in source_page
    assert 'source_path=RETRIEVE_CONFIG["source_path"]' in source_page
    assert 'index_path=RETRIEVE_CONFIG["index_path"]' in source_page
    assert 'rebuild_if_missing=True' in source_page
    assert 'rebuild_if_stale=True' in source_page


def test_source_preview_uses_selected_endpoint_env_bindings(monkeypatch):
    monkeypatch.setenv("GPT_41_MODEL", "agentic-sdk-gpt-4.1")
    monkeypatch.setenv("GPT_41_BASE_URL", "https://example.test/openai/gpt41")
    monkeypatch.setenv("GPT_41_API_KEY", "key-41")
    monkeypatch.setenv("EMBEDDED_DEPLOYMENT_NAME", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDED_ENDPOINT", "https://example.test/openai/embeddings")
    monkeypatch.setenv("EMBEDDED_API_KEY", "embed-key")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text"})
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "retrieve",
                "value": {
                    "semantic_support_files": "產品手冊.pdf",
                    "semantic_search_goal": "退款條件與保固限制",
                },
            },
        )
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "interactive"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "response_instruction": "先摘要重點，再引導使用者完成確認。",
                    "api_contracts": '[{"interaction_trigger":"需要確認資料","api_method":"POST","api_url":"https://example.test/api","component_fields":"name = 姓名"}]',
                },
            },
        )
        client.post(
            "/playground/builder/endpoints",
            json={
                "selections": {
                    "perceive": "gpt-41",
                    "retrieve": "embedded",
                    "action": "gpt-41",
                }
            },
        )
        source_page = client.get("/playground/source/preview").data.decode("utf-8")

    assert "import os" not in source_page
    assert 'TextPerceive(api_key="<PERCEIVE_API_KEY>", base_url="<PERCEIVE_API_BASE_URL>", model="<PERCEIVE_MODEL>"' in source_page
    assert 'NextStepPlan(api_key="<ACTION_API_KEY>", base_url="<ACTION_API_BASE_URL>", model="<ACTION_MODEL>"' in source_page
    assert 'SemanticRetrieve(' in source_page
    assert 'api_key="<RETRIEVE_API_KEY>"' in source_page
    assert 'base_url="<RETRIEVE_API_BASE_URL>"' in source_page
    assert 'embedding_model="<RETRIEVE_EMBEDDING_MODEL>"' in source_page
    assert 'source_path=RETRIEVE_CONFIG["source_path"]' in source_page
    assert 'index_path=RETRIEVE_CONFIG["index_path"]' in source_page
    assert 'ToolCallAction(api_key="<ACTION_API_KEY>", base_url="<ACTION_API_BASE_URL>", model="<ACTION_MODEL>", system_prompt="先摘要重點，再引導使用者完成確認。"' in source_page
    assert "並把 `api_key`、`base_url`、`model` 或 `embedding_model` 的 `<...>` 換成你的部署設定。" in source_page


def test_exported_source_imports_match_used_modules_for_representative_configs():
    cases = [
        [],
        [
            {"step": "input_type", "choice": "text"},
            {"step": "retrieve_policy", "choice": "keyword"},
            {"step": "retrieve", "value": {"keyword_pairs": "a = abc"}},
            {"step": "output_format", "choice": "free_text"},
            {"step": "failure_policy", "choice": "handoff"},
        ],
        [
            {"step": "input_type", "choice": "text"},
            {"step": "retrieve_policy", "choice": "semantic"},
            {"step": "retrieve", "value": {"semantic_support_files": "a.pdf", "semantic_search_goal": "退款條件"}},
            {"step": "output_format", "choice": "interactive"},
            {"step": "action", "value": {"response_instruction": "先摘要", "api_contracts": '[{"interaction_trigger":"確認","api_method":"POST","api_url":"https://example.test/api","component_fields":"name = 姓名"}]'}},
            {"step": "failure_policy", "choice": "retry"},
        ],
    ]

    app = create_app()

    for actions in cases:
        with app.test_client() as client:
            client.get("/playground/builder")
            for payload in actions:
                client.post("/playground/builder/state", json=payload)
            exported_source = client.post("/playground/source/export").data.decode("utf-8")

        assert _imported_module_names(exported_source) == _used_exported_module_names(exported_source)


def test_exported_source_imports_follow_workflow_role_order():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text"})
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "retrieve",
                "value": {
                    "semantic_support_files": "a.pdf",
                    "semantic_search_goal": "退款條件",
                },
            },
        )
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "interactive"})
        client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "response_instruction": "先摘要",
                    "api_contracts": '[{"interaction_trigger":"確認","api_method":"POST","api_url":"https://example.test/api","component_fields":"name = 姓名"}]',
                },
            },
        )
        client.post("/playground/builder/state", json={"step": "failure_policy", "choice": "retry"})
        exported_source = client.post("/playground/source/export").data.decode("utf-8")

    imported_names = _imported_module_names_in_order(exported_source)

    assert imported_names[:3] == [
        "TextPerceive",
        "NextStepPlan",
        "SemanticRetrieve",
    ]
    assert imported_names[-1] == "ToolCallAction"
    assert imported_names[3] in {"EvidenceCheckReflect", "ResponseCheckReflect"}


def test_builder_step3_semantic_upload_route_updates_state_and_source():
    app = create_app()

    with app.test_client() as client:
      client.get("/playground/builder")
      client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
      response = client.post(
          "/playground/builder/uploads",
          data={
              "files": [
                  (BytesIO(b"manual"), "產品手冊.pdf"),
                  (BytesIO(b"policy"), "退款政策.docx"),
              ]
          },
          content_type="multipart/form-data",
      )
      source_page = client.get("/playground/source/preview").data.decode("utf-8")
    builder_page = client.get("/playground/builder").data.decode("utf-8")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["uploaded_files"] == ["產品手冊.pdf", "退款政策.docx"]
    assert payload["semantic_support_files"] == ["產品手冊.pdf", "退款政策.docx"]
    state = _builder_form_state(builder_page)
    assert state == {"choices": {}, "values": {}}
    assert '"產品手冊.pdf"' in source_page
    assert '"退款政策.docx"' in source_page


def test_builder_step6_endpoint_selection_roundtrips_before_runner(monkeypatch):
    monkeypatch.setenv("GPT_54_MODEL", "agentic-sdk-gpt-5.4")
    monkeypatch.setenv("GPT_54_BASE_URL", "https://example.test/openai/gpt54")
    monkeypatch.setenv("GPT_54_API_KEY", "key-54")
    monkeypatch.setenv("GPT_41_MODEL", "agentic-sdk-gpt-4.1")
    monkeypatch.setenv("GPT_41_BASE_URL", "https://example.test/openai/gpt41")
    monkeypatch.setenv("GPT_41_API_KEY", "key-41")
    monkeypatch.setenv("EMBEDDED_DEPLOYMENT_NAME", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDED_ENDPOINT", "https://example.test/openai/embeddings")
    monkeypatch.setenv("EMBEDDED_API_KEY", "embed-key")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text"})
        retrieve_response = client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "free_text"})
        failure_response = client.post("/playground/builder/state", json={"step": "failure_policy", "choice": "retry"})

        endpoint_state = failure_response.get_json()["builder_endpoint_state"]

        assert [requirement["role"] for requirement in endpoint_state["requirements"]] == ["perceive", "retrieve", "action"]
        assert {endpoint["label"] for endpoint in endpoint_state["endpoints"]} >= {"gpt-4.1", "gpt-5.4"}
        retrieve_requirement = next(requirement for requirement in endpoint_state["requirements"] if requirement["role"] == "retrieve")
        assert {endpoint["label"] for endpoint in retrieve_requirement["options"]} >= {"text-embedding-3-large"}

        endpoint_response = client.post(
            "/playground/builder/endpoints",
            json={
                "selections": {
                    "perceive": "gpt-41",
                    "retrieve": "embedded",
                    "action": "gpt-41",
                }
            },
        )
        refreshed_page = client.get("/playground/builder").data.decode("utf-8")

    assert endpoint_response.status_code == 200
    payload = endpoint_response.get_json()
    assert payload["configured"] is True
    assert payload["selections"] == {
        "perceive": "gpt-41",
        "retrieve": "embedded",
        "action": "gpt-41",
    }
    refreshed_state = _builder_endpoint_state(refreshed_page)
    assert refreshed_state["requirements"] == []
    assert refreshed_state["selections"] == {}


def test_builder_step6_marks_semantic_search_incomplete_without_uploaded_files(monkeypatch):
    monkeypatch.setenv("EMBEDDED_DEPLOYMENT_NAME", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDED_ENDPOINT", "https://example.test/openai/embeddings")
    monkeypatch.setenv("EMBEDDED_API_KEY", "embed-key")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        response = client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})

    assert response.status_code == 200
    payload = response.get_json()
    review_item = next(item for item in payload["builder_review_state"] if item["step_key"] == "retrieve_policy")
    assert review_item["answer"] == "語意搜尋"
    assert review_item["completed"] is False
    assert review_item["detail"] == "請完成「要上傳哪些支援文件？」。"
    assert payload["builder_review_ready"] is False


def test_builder_step6_marks_semantic_search_complete_after_files_are_filled(monkeypatch):
    monkeypatch.setenv("EMBEDDED_DEPLOYMENT_NAME", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDED_ENDPOINT", "https://example.test/openai/embeddings")
    monkeypatch.setenv("EMBEDDED_API_KEY", "embed-key")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        response = client.post(
            "/playground/builder/state",
            json={
                "step": "retrieve",
                "value": {
                    "semantic_support_files": "產品手冊.pdf\n退款政策.docx",
                    "semantic_search_goal": "退款條件與保固限制",
                },
            },
        )

    assert response.status_code == 200
    payload = response.get_json()
    review_item = next(item for item in payload["builder_review_state"] if item["step_key"] == "retrieve_policy")
    assert review_item["answer"] == "語意搜尋"
    assert review_item["completed"] is True
    assert review_item["detail"] == ""


def test_builder_step6_marks_interactive_output_incomplete_without_api_contract(monkeypatch):
    monkeypatch.setenv("GPT_54_MODEL", "agentic-sdk-gpt-5.4")
    monkeypatch.setenv("GPT_54_BASE_URL", "https://example.test/openai/gpt54")
    monkeypatch.setenv("GPT_54_API_KEY", "key-54")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        response = client.post("/playground/builder/state", json={"step": "output_format", "choice": "interactive"})

    assert response.status_code == 200
    payload = response.get_json()
    review_item = next(item for item in payload["builder_review_state"] if item["step_key"] == "output_format")
    assert review_item["answer"] == "可互動元件"
    assert review_item["completed"] is False
    assert review_item["detail"] == "請至少完成一組「API URL」與「需要收集的資訊」。"
    assert payload["builder_review_ready"] is False


def test_builder_step6_marks_interactive_output_complete_after_contract_is_filled(monkeypatch):
    monkeypatch.setenv("GPT_54_MODEL", "agentic-sdk-gpt-5.4")
    monkeypatch.setenv("GPT_54_BASE_URL", "https://example.test/openai/gpt54")
    monkeypatch.setenv("GPT_54_API_KEY", "key-54")

    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        client.post("/playground/builder/state", json={"step": "output_format", "choice": "interactive"})
        response = client.post(
            "/playground/builder/state",
            json={
                "step": "action",
                "value": {
                    "response_instruction": "先摘要重點，再引導使用者完成確認。",
                    "api_contracts": '[{"interaction_trigger":"需要確認資料","api_method":"POST","api_url":"https://example.test/api","component_fields":"name = 姓名"}]',
                },
            },
        )

    assert response.status_code == 200
    payload = response.get_json()
    review_item = next(item for item in payload["builder_review_state"] if item["step_key"] == "output_format")
    assert review_item["answer"] == "可互動元件"
    assert review_item["completed"] is True
    assert review_item["detail"] == ""


def test_failure_policy_toggle_back_to_retry_keeps_reflect_model_requirement():
    app = create_app()

    with app.test_client() as client:
        client.get("/playground/builder")
        first_retry = client.post("/playground/builder/state", json={"step": "failure_policy", "choice": "retry"}).get_json()
        handoff = client.post("/playground/builder/state", json={"step": "failure_policy", "choice": "handoff"}).get_json()
        second_retry = client.post("/playground/builder/state", json={"step": "failure_policy", "choice": "retry"}).get_json()

    assert [requirement["role"] for requirement in first_retry["builder_endpoint_state"]["requirements"]] == ["reflect"]
    assert [requirement["role"] for requirement in handoff["builder_endpoint_state"]["requirements"]] == ["reflect"]
    assert [requirement["role"] for requirement in second_retry["builder_endpoint_state"]["requirements"]] == ["reflect"]


def test_builder_refresh_preserves_loaded_configuration():
    app = create_app()
    loaded_source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)

    with app.test_client() as client:
        with client.session_transaction() as session_state:
            session_state["python_source"] = loaded_source
            session_state["source_origin"] = "aihub_loaded"
        builder_page = client.get("/playground/builder").data.decode("utf-8")

    state = _builder_form_state(builder_page)
    assert state["choices"]["retrieve_policy"] == "semantic"