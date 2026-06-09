"""A-01 — Foundry client 抽象與 Mock 行為驗證。"""

from __future__ import annotations

import pytest

from agentic_sdk.config import Settings
from agentic_sdk.workflow.llm import (
    MockFoundryClient,
    RealFoundryClient,
    get_foundry_client,
)


def test_mock_foundry_label_includes_mock():
    assert "mock" in MockFoundryClient().label.lower()


def test_mock_foundry_plan_first_visit_returns_retrieve():
    mock = MockFoundryClient()
    resp = mock.chat(system="PLAN: route", user="hello")
    decision = resp.as_json()
    assert decision["next_node"] == "retrieve"


def test_mock_foundry_plan_second_visit_returns_action():
    mock = MockFoundryClient()
    mock.chat(system="PLAN: route", user="hello")  # visit 1
    resp = mock.chat(system="PLAN: route", user="hello again")  # visit 2
    assert resp.as_json()["next_node"] == "action"


def test_mock_foundry_reflect_pass_returns_none_next():
    mock = MockFoundryClient()
    resp = mock.chat(system="REFLECT: review", user="action ok content")
    assert resp.as_json()["verdict"] == "pass"
    assert resp.as_json()["next_node"] is None


def test_mock_foundry_reflect_error_routes_back_to_plan():
    mock = MockFoundryClient()
    resp = mock.chat(system="REFLECT: review", user="ERROR connection refused")
    assert resp.as_json()["verdict"] == "fail"
    assert resp.as_json()["next_node"] == "plan"


def test_mock_foundry_token_counts_populated():
    resp = MockFoundryClient().chat(system="PLAN:", user="x" * 100)
    assert resp.input_tokens is not None and resp.input_tokens > 0
    assert resp.output_tokens is not None and resp.output_tokens > 0


def test_get_foundry_client_returns_mock_when_key_missing():
    settings = Settings(_env_file=None, azure_foundry_api_key="")
    client = get_foundry_client(settings)
    assert isinstance(client, MockFoundryClient)


def test_get_foundry_client_returns_mock_when_forced():
    settings = Settings(
        _env_file=None,
        azure_foundry_api_key="sk-real",
        azure_foundry_endpoint="https://x.openai.azure.com/",
        workflow_force_mock_foundry=True,
    )
    client = get_foundry_client(settings)
    assert isinstance(client, MockFoundryClient)


def test_get_foundry_client_returns_real_when_key_present(monkeypatch):
    settings = Settings(
        _env_file=None,
        azure_foundry_api_key="sk-real",
        azure_foundry_endpoint="https://x.openai.azure.com/",
        workflow_force_mock_foundry=False,
    )
    client = get_foundry_client(settings)
    assert isinstance(client, RealFoundryClient)
    assert "azure_openai" in client.label


def test_real_foundry_requires_endpoint_and_key():
    settings = Settings(_env_file=None, azure_foundry_api_key="", azure_foundry_endpoint="")
    with pytest.raises(RuntimeError, match="Azure Foundry"):
        RealFoundryClient(settings)
