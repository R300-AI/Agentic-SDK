import pytest

from playground import create_app


pytestmark = pytest.mark.skip(reason="Legacy playground v1 contract predates the restored v2 release.")


def test_runner_keyboard_and_status_contract():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/run")

    page = response.data
    assert response.status_code == 200
    assert b"<label for=\"runner-message\">" in page
    assert b"<label for=\"runner-attachments\">" in page
    assert "type=\"submit\">產生回覆".encode("utf-8") in page
    assert b"role=\"status\" data-run-status" in page
    assert b"aria-live=\"polite\"" in page
    assert b"aria-expanded=\"false\"" in page
    assert b"aria-controls=\"trust-basis-panel\"" in page
    assert b"data-history-list" not in page


def test_builder_keyboard_navigation_contract():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/builder")

    page = response.data
    assert response.status_code == 200
    assert "aria-label=\"建立流程步驟\"".encode("utf-8") in page
    assert b"aria-current=\"step\"" in page
    assert b"data-progress-step=\"task_type\"" in page
    assert b"data-step-back" in page
    assert b"data-step-continue" in page
    assert b"disabled" in page
