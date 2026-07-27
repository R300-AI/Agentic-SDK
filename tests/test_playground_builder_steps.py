import json
from io import BytesIO
import re

from playground import create_app
from playground.services.source_builder import get_builder_steps


def _builder_form_state(html: str) -> dict[str, object]:
    match = re.search(r'<script id="builder-form-state" type="application/json" data-builder-form-state>(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


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
        "Q6: 現在可以試跑了嗎？",
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
        builder_page = client.get("/playground/builder").data.decode("utf-8")
        source_page = client.get("/playground/source/preview").data.decode("utf-8")
        runner_page = client.get("/playground/run").data.decode("utf-8")

    assert 'name="starter_questions"' in builder_page
    assert "對話開始前，要先放哪些常用問題？" in builder_page
    assert "這份內容的重點是什麼？" in builder_page
    assert "RUNNER_CONFIG" in source_page
    assert '"starter_questions": [' in source_page
    assert "下一步該怎麼做？" in source_page
    assert 'data-starter-questions' in runner_page
    assert 'data-starter-question-button' in runner_page
    assert "這份內容的重點是什麼？" in runner_page


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
        builder_page = client.get("/playground/builder").data.decode("utf-8")
        source_page = client.get("/playground/source/preview").data.decode("utf-8")

    state = _builder_form_state(builder_page)
    assert state["choices"]["retrieve_policy"] == "semantic"
    assert state["values"]["retrieve"]["semantic_support_files"] == "產品手冊.pdf\n退款政策.docx"
    assert state["values"]["retrieve"]["semantic_search_goal"] == "退款條件與保固限制"
    assert 'RETRIEVE_CONFIG = {' in source_page
    assert '"semantic_support_files": [' in source_page
    assert '"產品手冊.pdf"' in source_page
    assert '"退款政策.docx"' in source_page
    assert '"semantic_search_goal": "退款條件與保固限制"' in source_page
    assert 'SemanticRetrieve(' in source_page
    assert 'embedding_model="<填入 embedding model>"' in source_page
    assert 'source_path="./knowledge"' in source_page
    assert 'index_path="./.agentic/semantic_index"' in source_page
    assert 'rebuild_if_missing=True' in source_page
    assert 'rebuild_if_stale=True' in source_page


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
      builder_page = client.get("/playground/builder").data.decode("utf-8")
      source_page = client.get("/playground/source/preview").data.decode("utf-8")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["updated"] is True
    assert payload["uploaded_files"] == ["產品手冊.pdf", "退款政策.docx"]
    assert payload["semantic_support_files"] == ["產品手冊.pdf", "退款政策.docx"]
    state = _builder_form_state(builder_page)
    assert state["values"]["retrieve"]["semantic_support_files"] == "產品手冊.pdf\n退款政策.docx"
    assert '"產品手冊.pdf"' in source_page
    assert '"退款政策.docx"' in source_page