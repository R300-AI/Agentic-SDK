from __future__ import annotations

from playground.app import create_app


def test_interactive_echo_is_disabled_outside_test_mode(monkeypatch):
    monkeypatch.delenv("PLAYGROUND_ENABLE_TEST_SUPPORT_ROUTES", raising=False)
    app = create_app()

    response = app.test_client().post("/playground/test-support/interactive-echo", json={"approved": True})

    assert response.status_code == 404


def test_interactive_echo_returns_only_the_submitted_test_payload():
    app = create_app()
    app.config.update(TESTING=True)

    response = app.test_client().post(
        "/playground/test-support/interactive-echo?case=interactive-boolean",
        json={"approved": True},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "accepted": True,
        "received": {"approved": True},
        "test_case_id": "interactive-boolean",
    }