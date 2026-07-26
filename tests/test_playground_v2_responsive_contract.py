from playground_v2 import create_app


def test_mobile_responsive_css_contract():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/static/css/app.css")

    css = response.data
    assert response.status_code == 200
    assert b"@media (max-width: 980px)" in css
    assert b".runner-layout" in css
    assert b"grid-template-columns: 1fr" in css
    assert b".progress-rail" in css
    assert b".progress-step-list::before" in css
    assert b"grid-template-columns: repeat(9" in css
    assert b".structured-input-grid" in css
    assert b"flex-direction: column" in css


def test_runner_mobile_safe_primary_regions_exist_before_side_panel():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        response = client.get("/playground/run")

    page = response.data.decode("utf-8")
    assert response.status_code == 200
    assert page.index("task-surface") < page.index("runner-side-panel")
    assert page.index("chat-thread") < page.index("runner-message")
    assert page.index("data-user-message") < page.index("runner-message")
    assert page.index("data-result-surface") < page.index("runner-message")
    assert "data-result-thread" in page
    assert "composer-main-row" in page
    assert "產生回覆" in page
