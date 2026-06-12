from __future__ import annotations

from agentic_sdk import KnowledgeBaseRegistry, build_capability_document
from agentic_sdk.workflow import Workflow, WorkflowConfig, NodeSpec


def test_capability_document_exposes_stage_ii_refs() -> None:
    capabilities = build_capability_document()

    assert capabilities["schema_version"] == 1
    assert {item["role"] for item in capabilities["node_definitions"]} >= {
        "perceive",
        "plan",
        "retrieve",
        "reflect",
        "action",
    }
    assert {item["ref"] for item in capabilities["retrieve_strategy_refs"]} >= {
        "lexical_file_kb",
        "hybrid_memory_kb",
        "semantic_vector_kb",
        "remote_search",
    }
    assert any(
        item["ref"] == "shoe_store_catalog_search"
        and item["strategy_ref"] == "lexical_file_kb"
        for item in capabilities["retrieve_template_refs"]
    )
    assert any(item["ref"] == "shoe_store" for item in capabilities["knowledge_base_refs"])
    assert capabilities["export_capabilities"]["runnable_bundle"] is True
    assert "registries.yaml" in capabilities["export_capabilities"]["required_files"]
    assert capabilities["feature_flags"]["inline_python_hosted"] is False


def test_capabilities_endpoint_shape(make_client, respx_mock) -> None:
    with make_client() as client:
        response = client.get("/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    retrieve_node = next(
        item for item in body["node_definitions"] if item["role"] == "retrieve"
    )
    assert retrieve_node["params_schema"]["retrieve_template_ref"]["ref_kind"] == "retrieve_template"
    assert retrieve_node["params_schema"]["knowledge_base_ref"]["ref_kind"] == "knowledge_base"
    assert body["feature_flags"]["remote_search_retrieve"] is False


def test_knowledge_base_preview_endpoint(make_client, respx_mock) -> None:
    with make_client() as client:
        response = client.get(
            "/v1/knowledge-bases/shoe_store/preview",
            params={"query": "扁平足 跑鞋", "top_k": 2},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_base_ref"] == "shoe_store"
    assert body["hits"]
    assert body["hits"][0]["source"] == "knowledge_base"


def test_knowledge_base_registry_loads_shoe_store() -> None:
    registry = KnowledgeBaseRegistry()
    kb = registry.load("shoe_store")

    assert kb.name == "shoe_store"
    assert len(kb.entries) >= 1


def test_workflow_config_accepts_knowledge_base_ref() -> None:
    config = WorkflowConfig(
        nodes={
            "retrieve": NodeSpec(
                type="builtin.retrieve",
                params={
                    "retrieve_template_ref": "shoe_store_catalog_search",
                    "retrieve_strategy_ref": "lexical_file_kb",
                    "knowledge_base_ref": "shoe_store",
                    "top_k": 2,
                },
            )
        }
    )

    workflow = Workflow.from_config(config)
    result = workflow.run("我扁平足，想找適合久站的跑鞋")

    assert result.visit_counts["retrieve"] >= 1
    retrieved = [entry for entry in result.entries if entry.type == "retrieved"]
    assert retrieved
    assert retrieved[-1].metadata["kb_name"] == "shoe_store"
    assert retrieved[-1].metadata["kb_hit_count"] >= 1
