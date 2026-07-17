from playground_v2 import create_app


def test_three_pages_share_visual_system_assets_and_cta_language():
    app = create_app()

    with app.test_client() as client:
        entry = client.get("/playground/")
        builder = client.get("/playground/builder")
        client.post("/playground/start/anonymous")
        runner = client.get("/playground/run")
        css = client.get("/static/css/app.css")

    assert entry.status_code == 200
    assert builder.status_code == 200
    assert runner.status_code == 200
    assert css.status_code == 200

    for page in (entry.data, builder.data, runner.data):
        assert b"/static/css/app.css" in page
        assert b"button" in page

    assert b"entry-card" in entry.data
    assert b"builder-stage" in builder.data
    assert b"task-surface" in runner.data
    assert b"button-primary" in entry.data
    assert b"button-primary" in builder.data
    assert b"button-primary" in runner.data

    css_text = css.data
    assert b"--fluent-blue" in css_text
    assert b"--amd-red" in css_text
    assert b"--amd-black" in css_text
    assert b"clip-path" in css_text
    assert b".progress-step-list::before" in css_text
    assert b"grid-template-columns: repeat(9" in css_text
    assert b"--surface" in css_text
    assert b"--line-soft" in css_text
    assert b"--radius" in css_text


def test_runner_readonly_visual_density_is_direct_use_first():
    app = create_app()

    with app.test_client() as client:
        response = client.get("/playground/run?mode=aihub_readonly")

    page = response.data
    assert response.status_code == 200
    assert b"task-surface" in page
    assert b"runner-side-panel" in page
    assert "Python 原始碼".encode("utf-8") not in page
    assert "匯出 .py".encode("utf-8") not in page
    assert "編輯設定".encode("utf-8") not in page
    assert b"Agentic SDK" not in page
    assert "程式碼".encode("utf-8") not in page
    assert b"from agentic_sdk" not in page


def test_runner_conversation_canvas_is_primary_surface():
    app = create_app()

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        runner = client.get("/playground/run")
        css = client.get("/static/css/app.css")

    assert runner.status_code == 200
    assert css.status_code == 200
    assert b"chat-thread" in runner.data
    assert b"data-result-thread hidden" in runner.data
    assert b"composer-main-row" in runner.data
    assert b"result-content" in runner.data
    assert b"rows=\"1\"" in runner.data
    assert b"grid-template-rows: auto minmax(0, 1fr) auto" in css.data
    assert b"max-height: calc(100vh - 7rem)" in css.data
    assert b".chat-thread" in css.data
    assert b"overflow: auto" in css.data
    assert b"min-height: 2.75rem" in css.data
    assert b"[hidden] { display: none !important; }" in css.data
    assert b".result-content table" in css.data
    assert b".result-choice-list" in css.data
