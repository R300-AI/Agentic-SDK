from fastapi.testclient import TestClient

from playground.main import app


def test_fastapi_main_serves_playground_builder() -> None:
    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    response = client.get("/playground/builder")
    assert response.status_code == 200
    assert "回覆風格與規範" in response.text
    assert "可互動元件 API" in response.text
    assert "互動面板進階配置" not in response.text