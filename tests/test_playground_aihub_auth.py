import os
from pathlib import Path

import httpx

from playground import create_app
from playground.routes import aihub as aihub_routes
from playground.routes import entry as entry_routes
from playground.routes import runner as runner_routes
from playground.services import aihub_client
from playground.services import aihub_bridge
from playground.services import key_vault_config


def test_create_app_loads_ai_hub_url_from_key_vault(monkeypatch):
    monkeypatch.delenv("AI_HUB_BASE_URL", raising=False)
    monkeypatch.delenv("AIHUB_BASE_URL", raising=False)
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setattr(
        key_vault_config,
        "_key_vault_values",
        lambda vault_name: {
            "AI-HUB-BASE-URL": "https://aihub.example",
            "AI-HUB-PLAYGROUND-ORIGIN": "https://playground.example",
        },
    )

    create_app()

    assert os.environ["AI_HUB_BASE_URL"] == "https://aihub.example"
    assert os.environ["AI_HUB_PLAYGROUND_ORIGIN"] == "https://playground.example"


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


def test_verify_handoff_token_calls_ai_hub_handoff_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout, follow_redirects):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout, "follow_redirects": follow_redirects})
        return httpx.Response(200, json={"valid": True, "username": "creator", "agent_id": "agent-1"})

    monkeypatch.setenv("AI_HUB_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    result = aihub_client.verify_handoff_token(
        "handoff-token",
        api_base_url="https://aihub.example/",
        origin="https://playground.example/",
    )

    assert result == {"username": "creator", "agent_id": "agent-1", "display_name": ""}
    assert calls == [
        {
            "url": "https://aihub.example/api/playground/handoff/verify",
            "json": {"token": "handoff-token"},
            "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
            "timeout": 1.25,
            "follow_redirects": True,
        }
    ]


def test_runner_greeting_prefers_display_name_when_present():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_request_context("/playground/run"):
        from flask import session
        session["ai_hub_username"] = "creator"
        session["ai_hub_display_name"] = "R300"

        assert runner_routes._runner_greeting() == "Hi! R300"


def test_runner_greeting_falls_back_to_username_when_display_name_blank():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_request_context("/playground/run"):
        from flask import session
        session["ai_hub_username"] = "creator"
        session["ai_hub_display_name"] = "  "

        assert runner_routes._runner_greeting() == "Hi! creator"


def test_runner_greeting_refreshes_display_name_from_credential_ticket(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    ticket = aihub_client.issue_credential_ticket("admin", "secret")
    issued = []

    monkeypatch.setattr(
        runner_routes,
        "verify_identity",
        lambda username, password, *, origin=None: {"username": username, "display_name": "R300-AI"},
    )
    monkeypatch.setattr(
        runner_routes,
        "issue_credential_ticket",
        lambda username, password, **kwargs: issued.append((username, password, kwargs)) or "refreshed-ticket",
    )

    with app.test_request_context("/playground/run", base_url="https://playground.example"):
        from flask import session
        session["ai_hub_username"] = "admin"
        session["ai_hub_credential_ticket"] = ticket

        assert runner_routes._runner_greeting() == "Hi! R300-AI"
        assert session["ai_hub_display_name"] == "R300-AI"
        assert session["ai_hub_credential_ticket"] == "refreshed-ticket"

    assert issued == [("admin", "secret", {"token": "", "api_base_url": "", "display_name": "R300-AI"})]


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
        workflow_name="Agent One",
        description="Demo agent",
        credentials=aihub_client.AiHubCredentials(username="creator", password="secret"),
        origin="https://playground.example/",
    )

    assert result["saved"] is True
    assert result["integration_status"] == "aihub"
    assert result["requires_real_aihub_api"] is False
    assert calls == [
        {
            "url": "https://aihub.example/api/playground/config/save",
            "json": {
                "username": "creator",
                "password": "secret",
                "python_source": "print('hello')",
                "workflow_name": "Agent One",
                "description": "Demo agent",
                "agent_id": "agent 1",
            },
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
        workflow_name="Playground Agent",
        description="",
        credentials=aihub_client.AiHubCredentials(username="creator", password="secret"),
        origin="https://playground.example/",
    )

    assert result["saved"] is True
    assert result["agent_id"] == "agent-new"
    assert calls[0]["url"] == "https://aihub.example/api/playground/config/save"
    assert "agent_id" not in calls[0]["json"]
    assert calls[0]["json"]["workflow_name"] == "Playground Agent"


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


def test_load_public_config_calls_ai_hub_public_load_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"agent_id": "agent 1", "agent_name": "Shared Agent", "python_source": "print('shared')"})

    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setenv("AI_HUB_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)

    loaded = aihub_client.load_public_config("agent 1", origin="https://playground.example/")

    assert loaded["loaded"] is True
    assert loaded["agent_name"] == "Shared Agent"
    assert loaded["python_source"] == "print('shared')"
    assert loaded["access_mode"] == "public_readonly"
    assert calls == [
        {
            "url": "https://aihub.example/api/playground/agents/agent%201/config/public/load",
            "json": {},
            "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
            "timeout": 1.25,
        }
    ]


def test_bundle_url_requests_call_ai_hub_storage_api(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"upload_url": "https://storage.example/upload", "upload_method": "PUT", "upload_headers": {"x-ms-blob-type": "BlockBlob"}})

    def fake_get(url, *, headers, timeout):
        calls.append({"method": "GET", "url": url, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"download_url": "https://storage.example/download", "download_method": "GET"})

    credentials = aihub_client.AiHubCredentials(username="creator", password="secret")
    monkeypatch.setenv("AI_HUB_BASE_URL", "https://aihub.example/")
    monkeypatch.delenv("AI_HUB_PLAYGROUND_ORIGIN", raising=False)
    monkeypatch.setenv("AI_HUB_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setattr(aihub_client.httpx, "post", fake_post)
    monkeypatch.setattr(aihub_client.httpx, "get", fake_get)

    upload = aihub_client.request_bundle_upload_url("agent 1", credentials=credentials, origin="https://playground.example/")
    download = aihub_client.request_bundle_download_url("agent 1", credentials=credentials, origin="https://playground.example/")

    assert upload["ok"] is True
    assert upload["upload_url"] == "https://storage.example/upload"
    assert download["ok"] is True
    assert download["download_url"] == "https://storage.example/download"
    assert calls[0] == {
        "method": "POST",
        "url": "https://aihub.example/api/playground/agents/agent%201/bundle/save",
        "json": {"username": "creator", "password": "secret"},
        "headers": {"Accept": "application/json", "Origin": "https://playground.example"},
        "timeout": 1.25,
    }
    assert calls[1] == {
        "method": "GET",
        "url": "https://aihub.example/api/playground/agents/agent%201/bundle/load",
        "headers": {
            "Accept": "application/json",
            "Origin": "https://playground.example",
            "X-Playground-Username": "creator",
            "X-Playground-Password": "secret",
        },
        "timeout": 1.25,
    }


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


def test_entry_page_supports_unknown_or_manual_choice():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get("/playground/", base_url="https://playground.example")

    assert response.status_code == 200


def test_start_anonymous_enters_builder_with_local_source():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post("/playground/start/anonymous", base_url="https://playground.example")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "anonymous"
            assert session["source_origin"] == "manual_new"
            assert "python_source" in session

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/builder")


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


def test_aihub_navigation_builder_accepts_json_payload(monkeypatch):
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
            json={"username": "creator", "password": "secret"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/builder")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["account_context_present"] is True
            assert "agent_id" not in session

    assert seen == [("creator", "secret", "https://playground.example/")]


def test_aihub_navigation_builder_accepts_handoff_token(monkeypatch):
    seen = []

    def fake_verify(token, *, api_base_url=None, origin=None):
        seen.append((token, api_base_url, origin))
        return {"username": "creator", "agent_id": ""}

    monkeypatch.setattr(entry_routes, "verify_handoff_token", fake_verify)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/builder",
            base_url="https://playground.example",
            data={"token": "handoff-token", "api_base_url": "https://aihub.example/"},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/builder")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["ai_hub_username"] == "creator"
            credentials = aihub_client.credentials_for_ticket(session["ai_hub_credential_ticket"])

    assert seen == [("handoff-token", "https://aihub.example", "https://playground.example/")]
    assert credentials is not None
    assert credentials.username == "creator"
    assert credentials.password == ""
    assert credentials.token == "handoff-token"
    assert credentials.api_base_url == "https://aihub.example"


def test_bridge_builder_url_enters_managed_builder():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/builder/?runtimeMode=managed&apiBase=https%3A%2F%2Faihub.example&token=bridge-token",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["runtime_mode"] == "managed"
            assert session["ai_hub_api_base"] == "https://aihub.example"
            assert session["ai_hub_credential_ticket"]
            assert "agent_id" not in session

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/builder")


def test_playground_builder_url_accepts_bridge_query():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/playground/builder?runtimeMode=managed&apiBase=https%3A%2F%2Faihub.example&token=bridge-token",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "manual_auth"
            assert session["runtime_mode"] == "managed"
            assert session["ai_hub_api_base"] == "https://aihub.example"
            assert session["ai_hub_credential_ticket"]

    assert response.status_code == 200


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


def test_aihub_navigation_runner_restores_semantic_bundle_runtime_paths(monkeypatch):
    semantic_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Semantic Agent",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    captured = {}

    monkeypatch.setattr(entry_routes, "verify_credentials", lambda username, password, *, origin=None: True)
    monkeypatch.setattr(
        entry_routes,
        "load_config",
        lambda agent_id, *, credentials=None, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Semantic Agent",
            "python_source": semantic_source,
        },
    )
    monkeypatch.setattr(
        entry_routes,
        "restore_runtime_bundle",
        lambda *, agent_id=None, credentials=None, origin=None: {
            "bundle_restored": True,
            "builder_upload_id": "restored-upload",
            "python_source": semantic_source,
            "bundle_source_file_count": 1,
            "bundle_vectorstore_file_count": 2,
        },
    )

    def fake_execute_python_source(python_source, **kwargs):
        captured.update(kwargs)
        return {"status": "ok", "final_message": "ok", "result": {}, "debug_messages": [], "process_events": []}

    monkeypatch.setattr(runner_routes, "execute_python_source", fake_execute_python_source)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            json={"username": "creator", "password": "secret", "agent_id": "agent-1"},
        )
        assert response.status_code == 302
        execute_response = client.post("/playground/run/execute", base_url="https://playground.example", json={"message": "policy?"})

    assert execute_response.status_code == 200
    semantic_sources = [Path(item).as_posix() for item in captured["semantic_sources"]]
    semantic_saved_path = Path(captured["semantic_saved_path"]).as_posix()
    assert semantic_sources[0].endswith("semantic-runtime/restored-upload/source-files")
    assert semantic_saved_path.endswith("semantic-runtime/restored-upload")


def test_aihub_navigation_runner_keeps_latest_config_source_when_bundle_has_stale_recipe(monkeypatch):
    latest_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="New Gallery Name",
    task_goal="New summary from AI Hub config.",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    stale_bundle_source = latest_source.replace("New Gallery Name", "Old Bundle Name").replace("New summary from AI Hub config.", "Old bundle summary.")

    monkeypatch.setattr(entry_routes, "verify_credentials", lambda username, password, *, origin=None: True)
    monkeypatch.setattr(
        entry_routes,
        "load_config",
        lambda agent_id, *, credentials=None, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "New Gallery Name",
            "python_source": latest_source,
        },
    )
    monkeypatch.setattr(
        entry_routes,
        "restore_runtime_bundle",
        lambda *, agent_id=None, credentials=None, origin=None: {
            "bundle_restored": True,
            "builder_upload_id": "restored-upload",
            "python_source": stale_bundle_source,
            "bundle_source_file_count": 1,
            "bundle_vectorstore_file_count": 2,
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            json={"username": "creator", "password": "secret", "agent_id": "agent-1"},
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            session_source = session["python_source"]
            builder_upload_id = session["builder_upload_id"]

    assert response.status_code == 302
    assert "New Gallery Name" in session_source
    assert "New summary from AI Hub config." in session_source
    assert "Old Bundle Name" not in session_source
    assert builder_upload_id == "restored-upload"


def test_aihub_navigation_runner_accepts_json_payload(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda username, password, *, origin=None: username == "creator" and password == "secret")
    monkeypatch.setattr(
        entry_routes,
        "load_config",
        lambda agent_id, *, credentials=None, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Agent One",
            "python_source": "print('loaded')",
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            json={"username": "creator", "password": "secret", "agent_id": "agent-1"},
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_editable"
            assert session["agent_id"] == "agent-1"
            assert session["source_origin"] == "aihub_loaded"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")


def test_aihub_navigation_runner_accepts_handoff_token(monkeypatch):
    seen_verify = []
    seen_load = []

    def fake_verify(token, *, api_base_url=None, origin=None):
        seen_verify.append((token, api_base_url, origin))
        return {"username": "creator", "agent_id": "agent-1"}

    def fake_load_config(agent_id, *, credentials=None, origin=None):
        seen_load.append({"agent_id": agent_id, "credentials": credentials, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('loaded')"}

    monkeypatch.setattr(entry_routes, "verify_handoff_token", fake_verify)
    monkeypatch.setattr(entry_routes, "load_config", fake_load_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            json={"token": "handoff-token", "api_base_url": "https://aihub.example/", "agent_id": "agent-1"},
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_editable"
            assert session["agent_id"] == "agent-1"
            assert session["source_origin"] == "aihub_loaded"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")
    assert seen_verify == [("handoff-token", "https://aihub.example", "https://playground.example/")]
    assert seen_load[0]["agent_id"] == "agent-1"
    assert seen_load[0]["credentials"].username == "creator"
    assert seen_load[0]["credentials"].password == ""
    assert seen_load[0]["credentials"].token == "handoff-token"
    assert seen_load[0]["credentials"].api_base_url == "https://aihub.example"


def test_bridge_runner_edit_loads_agent_with_token(monkeypatch):
    seen_load = []
    seen_verify = []

    def fake_load_config(agent_id, *, credentials=None, origin=None):
        seen_load.append({"agent_id": agent_id, "credentials": credentials, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('loaded')"}

    def fake_verify_handoff_token(token, *, api_base_url=None, origin=None):
        seen_verify.append((token, api_base_url, origin))
        return {"username": "creator", "agent_id": "agent-1", "display_name": "R300"}

    monkeypatch.setattr(aihub_bridge, "load_config", fake_load_config)
    monkeypatch.setattr(aihub_bridge, "verify_handoff_token", fake_verify_handoff_token)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/runner/?mode=edit&runtimeMode=managed&apiBase=https%3A%2F%2Faihub.example&token=bridge-token&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_editable"
            assert session["account_context_present"] is True
            assert session["agent_id"] == "agent-1"
            assert session["ai_hub_username"] == "creator"
            assert session["ai_hub_display_name"] == "R300"
            assert session["source_origin"] == "aihub_loaded"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")
    assert seen_verify == [("bridge-token", "https://aihub.example", "https://playground.example/")]
    assert seen_load[0]["agent_id"] == "agent-1"
    assert seen_load[0]["credentials"].username == "creator"
    assert seen_load[0]["credentials"].display_name == "R300"
    assert seen_load[0]["credentials"].token == "bridge-token"
    assert seen_load[0]["credentials"].api_base_url == "https://aihub.example"


def test_bridge_runner_read_hides_owner_only_controls(monkeypatch):
    python_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction

workflow = Workflow(
    workflow_name="Shared Chat Agent",
    task_goal="Answer shared chat requests.",
    action=DirectAnswerAction(),
)
"""

    monkeypatch.setattr(
        aihub_bridge,
        "load_public_config",
        lambda agent_id, *, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Shared Chat Agent",
            "python_source": python_source,
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/playground/run?owner=creator&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_readonly"
            assert session["account_context_present"] is False
            assert session["source_origin"] == "aihub_shared_readonly"

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Shared Chat Agent" in body
    assert "data-save-action" not in body
    assert "data-reload-action" not in body
    assert "data-code-preview-open" not in body
    assert "編輯設定" not in body
    assert "data-save-login-modal" not in body


def test_bridge_runner_edit_keeps_latest_config_source_when_bundle_has_stale_recipe(monkeypatch):
    latest_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Bridge Fresh Name",
    task_goal="Bridge fresh summary.",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    stale_bundle_source = latest_source.replace("Bridge Fresh Name", "Bridge Old Name").replace("Bridge fresh summary.", "Bridge old summary.")

    monkeypatch.setattr(
        aihub_bridge,
        "load_config",
        lambda agent_id, *, credentials=None, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Bridge Fresh Name",
            "python_source": latest_source,
        },
    )
    monkeypatch.setattr(
        aihub_bridge,
        "restore_runtime_bundle",
        lambda *, agent_id=None, credentials=None, origin=None: {
            "bundle_restored": True,
            "builder_upload_id": "bridge-upload",
            "python_source": stale_bundle_source,
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/runner/?mode=edit&runtimeMode=managed&apiBase=https%3A%2F%2Faihub.example&token=bridge-token&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            session_source = session["python_source"]
            builder_upload_id = session["builder_upload_id"]

    assert response.status_code == 302
    assert "Bridge Fresh Name" in session_source
    assert "Bridge fresh summary." in session_source
    assert "Bridge Old Name" not in session_source
    assert builder_upload_id == "bridge-upload"


def test_playground_runner_edit_accepts_bridge_query(monkeypatch):
    seen_load = []

    def fake_load_config(agent_id, *, credentials=None, origin=None):
        seen_load.append({"agent_id": agent_id, "credentials": credentials, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Agent One", "python_source": "print('loaded')"}

    monkeypatch.setattr(aihub_bridge, "load_config", fake_load_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/playground/run?mode=edit&runtimeMode=managed&apiBase=https%3A%2F%2Faihub.example&token=bridge-token&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_editable"
            assert session["account_context_present"] is True
            assert session["agent_id"] == "agent-1"
            assert session["source_origin"] == "aihub_loaded"

    assert response.status_code == 200
    assert seen_load[0]["agent_id"] == "agent-1"
    assert seen_load[0]["credentials"].token == "bridge-token"
    assert seen_load[0]["credentials"].api_base_url == "https://aihub.example"


def test_bridge_runner_read_loads_public_agent(monkeypatch):
    seen_load = []

    def fake_load_public_config(agent_id, *, origin=None):
        seen_load.append({"agent_id": agent_id, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Shared Agent", "python_source": "print('shared')"}

    monkeypatch.setattr(aihub_bridge, "load_public_config", fake_load_public_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/runner/?mode=read&owner=creator&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_readonly"
            assert session["account_context_present"] is False
            assert session["agent_id"] == "agent-1"
            assert session["agent_owner"] == "creator"
            assert session["source_origin"] == "aihub_shared_readonly"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")
    assert seen_load == [{"agent_id": "agent-1", "origin": "https://playground.example/"}]


def test_legacy_aihub_deep_link_does_not_reuse_stale_source_for_different_agent():
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        with client.session_transaction(base_url="https://playground.example") as session:
            session["mode"] = "aihub_editable"
            session["account_context_present"] = True
            session["agent_id"] = "agent-old"
            session["agent_name"] = "Old Agent"
            session["python_source"] = "print('old agent source')"
            session["builder_upload_id"] = "old-upload"
            session["last_aihub_bundle_load"] = {"bundle_restored": True, "builder_upload_id": "old-upload"}
        response = client.get("/playground/run?mode=aihub_editable&agent_id=agent-new", base_url="https://playground.example")
        with client.session_transaction(base_url="https://playground.example") as session:
            agent_id = session["agent_id"]
            has_python_source = "python_source" in session
            has_builder_upload_id = "builder_upload_id" in session
            has_bundle_load = "last_aihub_bundle_load" in session

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/builder")
    assert agent_id == "agent-new"
    assert has_python_source is False
    assert has_builder_upload_id is False
    assert has_bundle_load is False


def test_playground_runner_read_accepts_bridge_query(monkeypatch):
    seen_load = []

    def fake_load_public_config(agent_id, *, origin=None):
        seen_load.append({"agent_id": agent_id, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Shared Agent", "python_source": "print('shared')"}

    monkeypatch.setattr(aihub_bridge, "load_public_config", fake_load_public_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/playground/run?mode=read&owner=creator&agentId=agent-1",
            base_url="https://playground.example",
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_readonly"
            assert session["account_context_present"] is False
            assert session["agent_id"] == "agent-1"
            assert session["agent_owner"] == "creator"
            assert session["source_origin"] == "aihub_shared_readonly"

    assert response.status_code == 200
    assert seen_load == [{"agent_id": "agent-1", "origin": "https://playground.example/"}]


def test_aihub_navigation_runner_requires_agent_id(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/runner",
            base_url="https://playground.example",
            data={"username": "creator", "password": "secret"},
        )

    assert response.status_code == 400
    assert "Missing AI Hub agent id." in response.get_data(as_text=True)


def test_shared_runner_loads_public_agent_as_read_only(monkeypatch):
    seen_load = []

    def fake_load_public_config(agent_id, *, origin=None):
        seen_load.append({"agent_id": agent_id, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Shared Agent", "python_source": "print('shared')"}

    monkeypatch.setattr(entry_routes, "load_public_config", fake_load_public_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.get(
            "/playground/aihub/navigation/shared-runner?agent_id=agent-1",
            base_url="https://playground.example",
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/playground/run")
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_readonly"
            assert session["account_context_present"] is False
            assert session["agent_id"] == "agent-1"
            assert session["agent_name"] == "Shared Agent"
            assert session["python_source"] == "print('shared')"
            assert session["source_origin"] == "aihub_shared_readonly"
            assert "ai_hub_credential_ticket" not in session
        runner_page = client.get("/playground/run", base_url="https://playground.example").get_data(as_text=True)
        builder_response = client.get("/playground/builder", base_url="https://playground.example")
        builder_state_response = client.post("/playground/builder/state", base_url="https://playground.example", json={"step": "output_format", "choice": "free_text"})
        source_preview_response = client.get("/playground/source/preview", base_url="https://playground.example")
        source_export_response = client.post("/playground/source/export", base_url="https://playground.example")

    assert seen_load == [{"agent_id": "agent-1", "origin": "https://playground.example/"}]
    assert "編輯設定" not in runner_page
    assert "預覽程式碼" not in runner_page
    assert "data-save-action" not in runner_page
    assert "產生回覆" in runner_page
    assert builder_response.status_code == 403
    assert builder_state_response.status_code == 403
    assert source_preview_response.status_code == 403
    assert source_export_response.status_code == 403


def test_shared_runner_accepts_post_json_payload(monkeypatch):
    seen_load = []

    def fake_load_public_config(agent_id, *, origin=None):
        seen_load.append({"agent_id": agent_id, "origin": origin})
        return {"loaded": True, "agent_id": agent_id, "agent_name": "Shared Agent", "python_source": "print('shared')"}

    monkeypatch.setattr(entry_routes, "load_public_config", fake_load_public_config)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/shared-runner",
            base_url="https://playground.example",
            json={"agent_id": "agent-1"},
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            assert session["mode"] == "aihub_readonly"
            assert session["agent_id"] == "agent-1"
            assert session["source_origin"] == "aihub_shared_readonly"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")
    assert seen_load == [{"agent_id": "agent-1", "origin": "https://playground.example/"}]


def test_shared_runner_accepts_post_form_payload(monkeypatch):
    monkeypatch.setattr(
        entry_routes,
        "load_public_config",
        lambda agent_id, *, origin=None: {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Shared Agent",
            "python_source": "print('shared')",
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        response = client.post(
            "/playground/aihub/navigation/shared-runner",
            base_url="https://playground.example",
            data={"agent_id": "agent-1"},
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/run")


def test_aihub_save_route_uses_login_ticket_and_session_source(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    seen = []

    def fake_save_config(agent_id, python_source, *, workflow_name=None, description=None, credentials=None, origin=None):
        seen.append({"agent_id": agent_id, "python_source": python_source, "workflow_name": workflow_name, "description": description, "credentials": credentials, "origin": origin})
        return {"agent_id": agent_id or "agent-new", "workflow_name": "Agent New", "description": description or "", "saved": True, "integration_status": "aihub", "requires_real_aihub_api": False}

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
    assert seen[0]["workflow_name"] == "Untitled Agent"
    assert seen[0]["description"] == ""
    assert seen[0]["origin"] == "https://playground.example/"
    assert seen[0]["credentials"].username == "creator"
    assert seen[0]["credentials"].password == "secret"


def test_aihub_save_route_reports_semantic_bundle_failure(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    semantic_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Semantic Agent",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""

    monkeypatch.setattr(
        aihub_routes,
        "save_config",
        lambda agent_id, python_source, *, workflow_name=None, description=None, credentials=None, origin=None: {
            "agent_id": agent_id or "agent-new",
            "workflow_name": workflow_name,
            "description": description or "",
            "saved": True,
            "integration_status": "aihub",
        },
    )
    monkeypatch.setattr(
        aihub_routes,
        "save_runtime_bundle",
        lambda **kwargs: {
            "bundle_saved": False,
            "bundle_error": "AI Hub bundle storage API is not available.",
            "bundle_error_code": "missing_bundle_api",
        },
    )
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", base_url="https://playground.example", data={"username": "creator", "password": "secret"})
        with client.session_transaction(base_url="https://playground.example") as session:
            session["mode"] = "manual_auth"
            session["python_source"] = semantic_source
            session["builder_upload_id"] = "upload-1"
        response = client.post("/playground/aihub/config/save", base_url="https://playground.example")

    assert response.status_code == 502
    assert response.json["config_saved"] is True
    assert response.json["saved"] is False
    assert response.json["bundle_saved"] is False
    assert response.json["error_code"] == "missing_bundle_api"


def test_aihub_save_route_prepares_semantic_saved_path_before_bundle_upload(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    semantic_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Semantic Agent",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    calls = []

    monkeypatch.setattr(
        aihub_routes,
        "save_config",
        lambda agent_id, python_source, *, workflow_name=None, description=None, credentials=None, origin=None: {
            "agent_id": agent_id or "agent-new",
            "workflow_name": workflow_name,
            "description": description or "",
            "saved": True,
            "integration_status": "aihub",
        },
    )

    def fake_prepare_semantic_runtime(python_source, **kwargs):
        calls.append(("prepare", kwargs))
        return {"prepared": True}

    def fake_save_runtime_bundle(**kwargs):
        calls.append(("save_bundle", kwargs))
        return {"bundle_saved": True, "bundle_source_file_count": 1, "bundle_vectorstore_file_count": 2}

    monkeypatch.setattr(aihub_routes, "prepare_semantic_runtime", fake_prepare_semantic_runtime)
    monkeypatch.setattr(aihub_routes, "save_runtime_bundle", fake_save_runtime_bundle)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", base_url="https://playground.example", data={"username": "creator", "password": "secret"})
        with client.session_transaction(base_url="https://playground.example") as session:
            session["mode"] = "manual_auth"
            session["python_source"] = semantic_source
            session["builder_upload_id"] = "upload-1"
        response = client.post("/playground/aihub/config/save", base_url="https://playground.example")

    assert response.status_code == 200
    assert response.json["saved"] is True
    assert [call[0] for call in calls] == ["prepare", "save_bundle"]
    prepare_kwargs = calls[0][1]
    assert Path(prepare_kwargs["semantic_sources"][0]).as_posix().endswith("semantic-runtime/upload-1/source-files")
    assert Path(prepare_kwargs["semantic_saved_path"]).as_posix().endswith("semantic-runtime/upload-1")


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
    picker_html = picker_response.get_data(as_text=True)
    assert "Select Your Agentic SDK Workflow" in picker_html
    assert "Agent One" in picker_html
    assert "選擇既有工作流" in picker_html
    assert '<label for="agent_id">選擇工作流</label>' not in picker_html
    assert "使用" in picker_html
    assert "建立新工作流" in picker_html
    assert "開始新建" in picker_html
    assert "編輯" not in picker_html
    assert "選擇要編輯的 Agent" not in picker_html
    assert "可載入既有 Agent 的 Playground 配置" not in picker_html
    assert "第一次儲存時 AI Hub 會建立 Agent" not in picker_html
    assert select_response.status_code == 302
    assert select_response.headers["Location"].endswith("/playground/run")
    assert reload_response.status_code == 200
    assert reload_response.json["loaded"] is True
    assert session_source == "print('reloaded')"


def test_agent_picker_select_clears_previous_bundle_runtime_for_plain_agent(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    monkeypatch.setattr(entry_routes, "list_agents", lambda *, credentials=None, origin=None: {"loaded": True, "items": [{"agent_id": "agent-plain", "agent_name": "Plain Agent"}]})
    monkeypatch.setattr(entry_routes, "load_config", lambda agent_id, *, credentials=None, origin=None: {"loaded": True, "agent_id": agent_id, "agent_name": "Plain Agent", "python_source": "print('plain')"})
    monkeypatch.setattr(entry_routes, "restore_runtime_bundle", lambda **kwargs: {"bundle_restored": False, "bundle_error": "No bundle for this agent."})
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        with client.session_transaction() as session:
            session["builder_upload_id"] = "old-upload"
            session["last_aihub_bundle_load"] = {"bundle_restored": True, "builder_upload_id": "old-upload"}
        response = client.post("/playground/agents/select", data={"agent_id": "agent-plain"})
        with client.session_transaction() as session:
            session_source = session["python_source"]
            has_builder_upload_id = "builder_upload_id" in session
            has_bundle_load = "last_aihub_bundle_load" in session

    assert response.status_code == 302
    assert session_source == "print('plain')"
    assert has_builder_upload_id is False
    assert has_bundle_load is False


def test_agent_picker_blocks_semantic_agent_when_bundle_restore_fails(monkeypatch):
    semantic_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Semantic Agent",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    monkeypatch.setattr(entry_routes, "list_agents", lambda *, credentials=None, origin=None: {"loaded": True, "items": [{"agent_id": "agent-1", "agent_name": "Semantic Agent"}]})
    monkeypatch.setattr(entry_routes, "load_config", lambda agent_id, *, credentials=None, origin=None: {"loaded": True, "agent_id": agent_id, "agent_name": "Semantic Agent", "python_source": semantic_source})
    monkeypatch.setattr(entry_routes, "restore_runtime_bundle", lambda **kwargs: {"bundle_restored": False, "bundle_error": "Bundle object was not found."})
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        response = client.post("/playground/agents/select", data={"agent_id": "agent-1"})

    assert response.status_code == 502
    html = response.get_data(as_text=True)
    assert "Bundle object was not found." in html
    assert "Semantic Agent" in html


def test_reload_blocks_semantic_agent_when_bundle_restore_fails(monkeypatch):
    semantic_source = """
from agentic_sdk import Workflow
from agentic_sdk.modules import SemanticRetrieve, DirectAnswerAction

workflow = Workflow(
    workflow_name="Semantic Agent",
    retrieve=SemanticRetrieve(sources=["./policy.md"]),
    action=DirectAnswerAction(),
)
"""
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    monkeypatch.setattr(aihub_routes, "load_config", lambda agent_id, *, credentials=None, origin=None: {"loaded": True, "agent_id": agent_id, "agent_name": "Semantic Agent", "python_source": semantic_source})
    monkeypatch.setattr(aihub_routes, "restore_runtime_bundle", lambda **kwargs: {"bundle_restored": False, "bundle_error": "Bundle object was not found."})
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        with client.session_transaction() as session:
            session["agent_id"] = "agent-1"
            session["builder_upload_id"] = "old-upload"
            session["last_aihub_bundle_load"] = {"bundle_restored": True, "builder_upload_id": "old-upload"}
        response = client.post("/playground/aihub/config/reload")
        with client.session_transaction() as session:
            has_builder_upload_id = "builder_upload_id" in session
            has_bundle_load = "last_aihub_bundle_load" in session

    assert response.status_code == 502
    assert response.json["loaded"] is False
    assert response.json["error"] == "Bundle object was not found."
    assert response.json["error_code"] == "semantic_bundle_not_restored"
    assert has_builder_upload_id is False
    assert has_bundle_load is False


def test_agent_picker_new_resets_selected_agent_and_enters_builder(monkeypatch):
    monkeypatch.setattr(entry_routes, "verify_credentials", lambda *args, **kwargs: True)
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/auth/login", data={"username": "creator", "password": "secret"})
        with client.session_transaction() as session:
            session["agent_id"] = "agent-1"
            session["agent_name"] = "Agent One"
            session["last_aihub_save"] = {"saved": True}
            session["python_source"] = "print('stale')"
            session["source_origin"] = "aihub_loaded"
        response = client.post("/playground/agents/new")
        with client.session_transaction() as session:
            assert "agent_id" not in session
            assert "agent_name" not in session
            assert "last_aihub_save" not in session
            assert session["mode"] == "manual_auth"
            assert session["source_origin"] == "manual_new"
            assert session["python_source"] != "print('stale')"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/playground/builder")


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


def test_aihub_login_route_authenticates_without_saving(monkeypatch):
    monkeypatch.setattr(aihub_routes, "verify_credentials", lambda username, password, origin=None: username == "creator" and password == "secret")
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with app.test_client() as client:
        client.post("/playground/start/anonymous", base_url="https://playground.example")
        with client.session_transaction(base_url="https://playground.example") as session:
            session["python_source"] = "print('hello')"
        response = client.post(
            "/playground/aihub/auth/login",
            base_url="https://playground.example",
            json={"username": "creator", "password": "secret"},
        )
        with client.session_transaction(base_url="https://playground.example") as session:
            saved_mode = session["mode"]
            saved_username = session["ai_hub_username"]
            saved_source = session["python_source"]
            pending_auto_save = session["pending_runner_auto_save"]

    assert response.status_code == 200
    assert response.json["authenticated"] is True
    assert saved_mode == "manual_auth"
    assert saved_username == "creator"
    assert saved_source == "print('hello')"
    assert pending_auto_save is True


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