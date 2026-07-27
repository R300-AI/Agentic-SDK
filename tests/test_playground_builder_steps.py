from playground import create_app
from playground.services.source_builder import get_builder_steps


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
        "Q1: 這個 Agent 要使用哪種記憶方式？",
        "Q2: 這個 Agent 要如何理解輸入？",
        "Q3: 回答前需要查資料嗎？",
        "Q4: 最後回覆要怎麼呈現給使用者？",
        "Q5: 答案不夠有把握時怎麼辦？",
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