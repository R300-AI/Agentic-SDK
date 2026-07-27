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


def test_builder_step2_exposes_json_and_image_configuration():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    assert response.status_code == 200
    page = response.data.decode("utf-8")
    assert "先抓出哪些資訊" in page
    assert "要留意的內容" in page
    assert "圖片要看什麼" in page
    assert "照片判讀重點" in page
    assert 'name="image_instruction"' in page
    assert 'data-visible-choices="text|text_image"' in page
    assert 'data-visible-choices="text_image"' in page
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
                    "welcome_message": "先看出客人想問什麼。",
                    "intent_pairs": "客人需求 = 客人想解決的問題或想買的東西（資料類型：文字）",
                    "importance": "2.0",
                },
            },
        )
        text_source = client.get("/playground/source/preview").data.decode("utf-8")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "text_image"})
        client.post("/playground/builder/state", json={"step": "perceive", "value": {"image_instruction": "請辨識圖片中的文字與異常。"}})
        image_source = client.get("/playground/source/preview").data.decode("utf-8")
        client.post("/playground/builder/state", json={"step": "input_type", "choice": "pass_through"})
        pass_source = client.get("/playground/source/preview").data.decode("utf-8")

    assert "TextPerceive(" in text_source
    assert "api_key=" in text_source
    assert "base_url=" in text_source
    assert "model=" in text_source
    assert "welcome_message=" in text_source
    assert "客人需求" in text_source
    assert "importance=2.0" in text_source
    assert "TextImagePerceive(" in image_source
    assert "image_instruction=" in image_source
    assert "PassThroughPerceive()" in pass_source
    assert "TextPerceive(" not in pass_source
    assert "TextImagePerceive(" not in pass_source