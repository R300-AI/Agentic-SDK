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

    monkeypatch.delenv("AI_HUB_BASE_URL")
    monkeypatch.delenv("AIHUB_BASE_URL", raising=False)
    assert aihub_client.verify_credentials("creator", "secret") is False


def test_save_config_calls_ai_hub_save_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"agent_id": "agent 1", "saved": True, "exported_at": "2026-07-27T00:00:00+00:00"})

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
            "url": "https://aihub.example/api/playground/config/save",
            "json": {"username": "creator", "password": "secret", "python_source": "print('hello')", "agent_id": "agent 1"},
            "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
            "timeout": 1.25,
        }
    ]


def test_save_config_can_create_agent_without_agent_id(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(201, json={"agent_id": "agent-new", "agent_name": "Playground Agent", "playground_exported_at": "2026-07-27T00:00:00Z"})

    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    result = aihub_client.save_config(
        None,
        "print('hello')",
        credentials=aihub_client.AiHubCredentials(username="creator", password="secret"),
        origin="https://playground.example/",
    )

    assert result["saved"] is True
    assert result["agent_id"] == "agent-new"
    assert calls[0]["url"] == "https://aihub.example/api/playground/config/save"
    assert "agent_id" not in calls[0]["json"]


def test_list_and_load_config_call_ai_hub_agent_apis(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/api/playground/agents"):
            return httpx.Response(200, json={"items": [{"agent_id": "agent-1", "agent_name": "Agent One"}]})
        return httpx.Response(200, json={"agent_id": "agent-1", "agent_name": "Agent One", "python_source": "print('loaded')", "playground_exported_at": "2026-07-27T00:00:00Z"})

    credentials = aihub_client.AiHubCredentials(username="creator", password="secret")
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    agents = aihub_client.list_agents(credentials=credentials, origin="https://playground.example/")
    loaded = aihub_client.load_config("agent 1", credentials=credentials, origin="https://playground.example/")

    assert agents["items"] == [{"agent_id": "agent-1", "agent_name": "Agent One"}]
    assert loaded["loaded"] is True
    assert loaded["python_source"] == "print('loaded')"
    assert calls[0]["url"] == "https://aihub.example/api/playground/agents"
    assert calls[1]["url"] == "https://aihub.example/api/playground/agents/agent%201/config/load"


def test_save_config_fails_closed_without_required_data(monkeypatch):
    calls = []
    monkeypatch.setattr(aihub_client.httpx, "post", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert aihub_client.save_config("agent-1", "")["error_code"] == "missing_python_source"
    assert aihub_client.save_config("agent-1", "print('hello')")["error_code"] == "missing_credentials"
    assert calls == []


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
        assert response.headers["Location"].endswith("/playground/agents")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["account_context_present"] is True
            assert session["ai_hub_credential_ticket"]

    assert seen == [("creator", "secret", "https://playground.example/")]


def test_aihub_navigation_builder_verifies_credentials_and_enters_builder(monkeypatch):
    seen = []

    def fake_verify(username, password, *, origin=None):
        seen.append((username, password, origin))
        return True

    monkeypatch.setattr(entry_routes, "verify_credentials", fake_verify)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/builder",
            base_url="https://playground.example",
            data={"username": "creator", "password": "secret"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/builder")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["account_context_present"] is True
            assert session["ai_hub_credential_ticket"]
            assert "agent_id" not in session

    assert seen == [("creator", "secret", "https://playground.example/")]


def test_aihub_navigation_runner_verifies_and_loads_agent(monkeypatch):
    seen_verify = []
    seen_load = []

    def fake_verify(username, password, *, origin=None):
        seen_verify.append((username, password, origin))
        return True

    def fake_load_config(agent_id, *, credentials=None, origin=None):
        seen_load.append({"agent_id": agent_id, "credentials": credentials, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('loaded')"}

    monkeypatch.setattr(entry_routes, "verify_credentials", fake_verify)
    monkeypatch.setattr(entry_routes, "load_config", fake_load_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            data={"username": "creator", "password": "secret", "agent_id": "agent-1"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/run")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_editable"
            assert session["account_context_present"] is True
            assert session["agent_id"] == "agent-1"
            assert session["agent_name"] == "Agent One"
            assert session["python_source"] == "print('loaded')"
            assert session["source_origin"] == "aihub_loaded"
            assert session["ai_hub_credential_ticket"]

    assert seen_verify == [("creator", "secret", "https://playground.example/")]
    assert seen_load[0]["agent_id"] == "agent-1"
    assert seen_load[0]["origin"] == "https://playground.example/"
    assert seen_load[0]["credentials"].username == "creator"
    assert seen_load[0]["credentials"].password == "secret"


def test_aihub_save_route_uses_login_ticket_and_session_source(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    seen = []

    def fake_save_config(agent_id, python_source, *, credentials=None, origin=None):
        seen.append({"agent_id": agent_id, "python_source": python_source, "credentials": credentials, "origin": origin})
        return {"agent_id": agent_id or "agent-new", "agent_name": "Agent New", "saved": True, "integration_status": "aihub", "requires_real_aihub_api": False}

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


def test_agent_picker_selects_and_reloads_existing_agent(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    monkeypatch.setattr(entry_routes, "list_agents", lambda *, credentials=None, origin=None: {"loaded": True, "items": [{"agent_id": "agent-1", "agent_name": "Agent One"}]})
    monkeypatch.setattr(aihub_routes, "load_config", lambda agent_id, *, credentials=None, origin=None: {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('reloaded')"})
    monkeypatch.setattr(entry_routes, "load_config", lambda agent_id, *, credentials=None, origin=None: {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('loaded')"})
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        picker_response = client.get("/playground/agents")
        select_response = client.post("/playground/agents/select", data={"agent_id": "agent-1"})
        reload_response = client.post("/playground/aihub/config/reload")
        with client.session_transaction() as session:
            session_source = session["python_source"]

    assert picker_response.status_code == 200
    assert "Agent One" in picker_response.get_data(as_text=True)
    assert select_response.status_code == 302
    assert select_response.headers["Location"].endswith("/playground/run")
    assert reload_response.status_code == 200
    assert reload_response.json["loaded"] is True
    assert session_source == "print('reloaded')"


def test_aihub_save_route_requires_login_ticket(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    monkeypatch.setattr(aihub_routes, "save_config", lambda *args, **kwargs: {"agent_id": "agent-new", "saved": True, "integration_status": "aihub", "requires_real_aihub_api": False})
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/start/anonymous")
        anonymous_response = client.post("/playground/aihub/config/save")

        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        with client.session_transaction() as session:
            session["python_source"] = "print('hello')"
        created_response = client.post("/playground/aihub/config/save")

        with client.session_transaction() as session:
            session.pop("ai_hub_credential_ticket", None)
            session["agent_id"] = "agent-1"
        missing_ticket_response = client.post("/playground/aihub/config/save")

    assert anonymous_response.status_code == 403
    assert anonymous_response.json["saved"] is False
    assert created_response.status_code == 200
    assert created_response.json["agent_id"] == "agent-new"
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