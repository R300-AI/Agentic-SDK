from playground_v2 import create_app


def test_runner_first_minute_acceptance_signals():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/run")

    assert response.status_code == 200
    page = response.data
    assert "產生可回覆客戶的內容".encode("utf-8") in page
    assert "客戶情境".encode("utf-8") in page
    assert "產生回覆".encode("utf-8") in page
    assert b"data-result-thread hidden" in page
    assert b"data-result-surface" in page
    assert b"data-result-message" in page
    assert "建議回覆".encode("utf-8") not in page
    assert "原因：".encode("utf-8") not in page
    assert "已整理一段可使用的回覆".encode("utf-8") not in page
    assert "請整理這次客戶詢問".encode("utf-8") not in page
    assert b"Agentic SDK" not in page
    assert "程式碼".encode("utf-8") not in page
    assert "匯出 .py".encode("utf-8") not in page
    assert b"from agentic_sdk" not in page


def test_direct_user_runner_hides_creator_language():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/run?mode=aihub_readonly")

    assert response.status_code == 200
    page = response.data
    assert b"WorkflowSettings" not in page
    assert "Python 原始碼".encode("utf-8") not in page
    assert "編輯設定".encode("utf-8") not in page
    assert "匯出 .py".encode("utf-8") not in page
    assert "產生回覆".encode("utf-8") in page
