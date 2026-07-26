import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

from playground import create_app
from playground.routes import aihub as aihub_routes
from playground.routes import entry as entry_routes
from playground.services import aihub_client


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_create_app_loads_ai_hub_url_from_project_env(monkeypatch):
    monkeypatch.delenv("AI_HUB_BASE_URL", raising=False)
    monkeypatch.delenv("AIHUB_BASE_URL", raising=False)
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    expected_base_url = dotenv_values(REPO_ROOT / ".env").get("AI_HUB_BASE_URL")
    expected_origin = dotenv_values(REPO_ROOT / ".env").get("AI_HUB_PLAYGROUND_ORIGIN")

    assert expected_base_url
    assert expected_origin

    create_app()

    assert os.environ["AI_HUB_BASE_URL"] == expected_base_url
    assert os.environ["AI_HUB_PLAYGROUND_ORIGIN"] == expected_origin


def test_verify_credentials_calls_ai_hub_auth_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"valid": True})

    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
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


def test_save_config_calls_ai_hub_save_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"saved": True, "exported_at": "2026-07-27T00:00:00+00:00"})

    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setenv("AI_HUB_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    result = aihub_client.save_config(
        "agent 1",
        "print('hello')",
        credentials=aihub_client.AiHubCredentials(username="creator", password="secret"),
        origin="https://playground.example/",
    )

    assert result["saved"] is True
    assert result["integration_status"] == "aihub"
    assert result["requires_real_aihub_api"] is False
    assert calls == [
        {
            "url": "https://aihub.example/api/playground/agents/agent%201/config/save",
            "json": {"username": "creator", "password": "secret", "python_source": "print('hello')"},
            "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
            "timeout": 1.25,
        }
    ]


def test_save_config_fails_closed_without_required_data(monkeypatch):
    calls = []
    monkeypatch.setattr(aihub_client.httpx, "post", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert aihub_client.save_config("", "print('hello')")["error_code"] == "missing_agent_id"
    assert aihub_client.save_config("agent-1", "")["error_code"] == "missing_python_source"
    assert aihub_client.save_config("agent-1", "print('hello')")["error_code"] == "missing_credentials"
    assert calls == []

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
            assert session["ai_hub_credential_ticket"]

    assert seen == [("creator", "secret", "https://playground.example/")]


def test_aihub_save_route_uses_login_ticket_and_session_source(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    seen = []

    def fake_save_config(agent_id, python_source, *, credentials=None, origin=None):
        seen.append({"agent_id": agent_id, "python_source": python_source, "credentials": credentials, "origin": origin})
        return {"agent_id": agent_id, "saved": True, "integration_status": "aihub", "requires_real_aihub_api": False}

    monkeypatch.setattr(aihub_routes, "save_config", fake_save_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        login_response = client.post(
            "/playground/auth/login",
            base_url="https://playground.example",
            data={"username": "creator", "password": "secret"},
        )
        assert login_response.status_code == 302
        with client.session_transaction(base_url="https://playground.example") as session:
            session["agent_id"] = "agent-1"
            session["python_source"] = "print('hello')"
        save_response = client.post("/playground/aihub/config/save", base_url="https://playground.example")

    assert save_response.status_code == 200
    assert save_response.json["saved"] is True
    assert seen[0]["agent_id"] == "agent-1"
    assert seen[0]["python_source"] == "print('hello')"
    assert seen[0]["origin"] == "https://playground.example/"
    assert seen[0]["credentials"].username == "creator"
    assert seen[0]["credentials"].password == "secret"


def test_aihub_save_route_requires_login_ticket_and_agent_id(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        anonymous_response = client.post("/playground/aihub/config/save")

        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        missing_agent_response = client.post("/playground/aihub/config/save")

        with client.session_transaction() as session:
            session.pop("ai_hub_credential_ticket", None)
            session["agent_id"] = "agent-1"
        missing_ticket_response = client.post("/playground/aihub/config/save")

    assert anonymous_response.status_code == 403
    assert anonymous_response.json["saved"] is False
    assert missing_agent_response.status_code == 400
    assert missing_agent_response.json["error"] == "Missing AI Hub agent id."
    assert missing_ticket_response.status_code == 401
    assert missing_ticket_response.json["error"] == "AI Hub login is required before saving."


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