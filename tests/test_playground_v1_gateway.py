from __future__ import annotations

import importlib.util

from playground_v1_gateway import create_app


def test_playground_v1_gateway_is_outside_sdk_core() -> None:
    assert importlib.util.find_spec("agentic_sdk.gateway") is None
    assert importlib.util.find_spec("playground_v1_gateway") is not None


def test_playground_v1_gateway_serves_capabilities_and_kb_preview() -> None:
    client = create_app().test_client()

    health = client.get("/healthz")
    capabilities = client.get("/v1/capabilities")
    preview = client.get("/v1/knowledge-bases/shoe_store/preview?query=久站&top_k=2")

    assert health.status_code == 200
    assert capabilities.status_code == 200
    assert capabilities.json["retrieve_template_refs"][0]["ref"] == "shoe_store_catalog_search"
    assert preview.status_code == 200
    assert preview.json["hits"][0]["title"] == "StablePro 機能健走鞋"


def test_playground_v1_gateway_runs_workflow_and_streams_events() -> None:
    client = create_app().test_client()

    run = client.post(
        "/v1/workflow/run",
        json={"user_message": "久站 扁平足", "workflow_yaml": "name: demo"},
    )

    assert run.status_code == 200
    workflow_id = run.json["workflow_id"]
    result = client.get(f"/v1/workflow/{workflow_id}/result")
    stream = client.get(f"/v1/workflow/{workflow_id}/stream")

    assert result.status_code == 200
    assert "StablePro" in result.json["final_message"]
    assert stream.status_code == 200
    assert b"workflow.node.start" in stream.data
    assert b"workflow.node.delta" in stream.data


def test_playground_v1_gateway_supports_local_agent_crud() -> None:
    client = create_app().test_client()

    created = client.post(
        "/api/me/agents",
        json={"agent_name": "demo", "description": "", "workflow_yaml": "name: demo"},
    )

    assert created.status_code == 200
    agent_id = created.json["agent_id"]
    assert client.get("/api/me/agents").json["items"][0]["agent_id"] == agent_id
    updated = client.put(
        f"/api/me/agents/{agent_id}",
        json={"agent_name": "updated", "description": "", "workflow_yaml": "name: updated"},
    )
    assert updated.json["agent_name"] == "updated"
    assert client.delete(f"/api/me/agents/{agent_id}").status_code == 204