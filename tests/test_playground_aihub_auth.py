import httpx

from playground import create_app
from playground.routes import entry as entry_routes
from playground.services import aihub_client


def test_verify_credentials_calls_ai_hub_auth_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"valid": True})

    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.setenv("AI_HUB_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    assert aihub_client.verify_credentials(" creator ", "secret", origin="https://playground.example/") is True
    assert calls == [
        {
            "url": "https://aihub.example/api/playground/auth/verify",
            "json": {"username": "creator", "password": "secret"},
            "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
            "timeout": 1.25,
        }
    ]


def test_verify_credentials_rejects_invalid_or_unreachable_ai_hub(monkeypatch):
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example")
    monkeypatch.setattr(aihub_client.httpx, "post", lambda *args, **kwargs: httpx.Response(200, json={"valid": False}))
    assert aihub_client.verify_credentials("creator", "wrong") is False

    def fail_post(*args, **kwargs):
        raise httpx.ConnectError("AI Hub unavailable")

    monkeypatch.setattr(aihub_client.httpx, "post", fail_post)
    assert aihub_client.verify_credentials("creator", "secret") is False

    monkeypatch.delenv("AI_HUB_BASE_URL")
    monkeypatch.delenv("AIHUB_BASE_URL", raising=False)
    assert aihub_client.verify_credentials("creator", "secret") is False


def test_login_uses_ai_hub_verification_before_entering_authenticated_mode(monkeypatch):
    seen = []

    def fake_verify(username, password, *, origin=None):
        seen.append((username, password, origin))
        return True

    monkeypatch.setattr(entry_routes, "verify_credentials", fake_verify)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/auth/login",
            base_url="https://playground.example",
            data={"username": "creator", "password": "secret"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/builder")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["account_context_present"] is True

    assert seen == [("creator", "secret", "https://playground.example/")]


def test_login_rejects_invalid_ai_hub_credentials(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: False)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/auth/login",
            data={"username": "creator", "password": "wrong"},
        )
        assert response.status_code == 400
        assert "We could not verify those AI Hub credentials" in response.get_data(as_text=True)
        with client.session_transaction() as session:
            assert "mode" not in session