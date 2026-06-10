"""tests/test_workflow_config.py — E-06 WorkflowConfig 驗收測試。

涵蓋:
- YAML / JSON round-trip(序列化 → 反序列化 → 再序列化結果一致)
- from_config() 端到端:以 MockFoundry 跑通一次工作流
- builtin action 類型切換(upstream_completion / foundry_completion)
- GateConfig 覆蓋生效驗證
- 自訂節點 import path(成功 / 失敗)
- 格式版本號碼不符拋例外
"""

from __future__ import annotations

import json

import pytest

from agentic_sdk.workflow import GateConfig, NodeSpec, Workflow, WorkflowConfig
from agentic_sdk.workflow.node import WorkflowAborted


# ── fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_config() -> WorkflowConfig:
    """最小合法 config:只覆蓋 action 為 foundry_completion、gate 調到最小。"""
    return WorkflowConfig(
        nodes={
            "action": NodeSpec(type="foundry_completion"),
        },
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
        entry="perceive",
    )


# ── YAML / JSON round-trip ────────────────────────────────────────────────────

def test_json_roundtrip(base_config: WorkflowConfig) -> None:
    serialized = base_config.to_json()
    restored = WorkflowConfig.from_json(serialized)
    assert restored.to_json() == serialized


def test_dict_roundtrip(base_config: WorkflowConfig) -> None:
    d = base_config.to_dict()
    restored = WorkflowConfig.from_dict(d)
    assert restored.to_dict() == d


def test_dict_preserves_gate_values(base_config: WorkflowConfig) -> None:
    d = base_config.to_dict()
    assert d["gates"]["max_node_hops"] == 20
    assert d["gates"]["max_revisit"] == 3
    assert d["gates"]["timeout_sec"] == 10.0


def test_dict_preserves_node_spec(base_config: WorkflowConfig) -> None:
    d = base_config.to_dict()
    assert d["nodes"]["action"]["type"] == "foundry_completion"


def test_version_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="version"):
        WorkflowConfig.from_dict({"version": "99", "nodes": {}, "gates": {}})


# ── from_config() 端到端(MockFoundry) ────────────────────────────────────────

@pytest.fixture
def mock_settings(monkeypatch):
    from agentic_sdk.config import Settings, get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("WORKFLOW_FORCE_MOCK_FOUNDRY", "true")
    monkeypatch.setenv("WORKFLOW_ACTION_BACKEND", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://mock.example.com/")
    monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "mock-key")
    s = Settings()
    yield s
    get_settings.cache_clear()


def test_from_config_runs_workflow(mock_settings) -> None:
    """from_config() 端到端 — 展示 Python SDK 標準用法。

    使用者自己建好 AzureOpenAI client(此處以 MagicMock 取代真實 client,介面相同),
    丟給 FoundryCompletionAction,再用 node_overrides 注入 Workflow。
    這就是 WorkflowConfig + Python SDK 的設計用意:
    YAML 描述拓樸與類型,Python 側可任意替換為帶有自訂 client 的活實例。
    """
    from unittest.mock import MagicMock

    from agentic_sdk.workflow.nodes.action import FoundryCompletionAction

    # 1. 使用者建立 AzureOpenAI client(測試用 MagicMock 取代)
    fake_message = MagicMock(content="測試回覆")
    fake_choice = MagicMock(message=fake_message)
    fake_completion = MagicMock(
        choices=[fake_choice],
        usage=None,
        model="gpt-4o-mini",
    )
    azure_client = MagicMock()
    azure_client.chat.completions.create.return_value = fake_completion

    # 2. 用該 client 建立 action node
    action = FoundryCompletionAction(settings=mock_settings, client=azure_client)

    # 3. 用 WorkflowConfig 描述拓樸,Python 側注入 node_overrides
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="foundry_completion")},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(
        config,
        settings=mock_settings,
        node_overrides={"action": action},
    )
    result = wf.run("測試 from_config")

    assert not result.aborted
    assert result.final_message == "測試回覆"
    azure_client.chat.completions.create.assert_called_once()


def test_from_config_empty_nodes_uses_defaults(mock_settings) -> None:
    """nodes 全空時,from_config 應補回所有節點的 DEFAULT。"""
    config = WorkflowConfig(
        nodes={},
        gates=GateConfig(max_node_hops=20, max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    assert set(wf.nodes.keys()) == {"perceive", "plan", "retrieve", "reflect", "action"}


def test_from_config_gate_override_aborts(mock_settings) -> None:
    """max_revisit=1 時,工作流應在 plan 第二次進入前被閘門中止。"""
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="foundry_completion")},
        gates=GateConfig(max_node_hops=50, max_revisit=1, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    result = wf.run("測試閘門")
    assert result.aborted
    assert result.abort_reason


# ── builtin action 類型切換 ───────────────────────────────────────────────────

def test_node_spec_upstream_completion_type(mock_settings) -> None:
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="upstream_completion")},
        gates=GateConfig(max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    from agentic_sdk.workflow.nodes.action import UpstreamCompletionAction
    assert isinstance(wf.nodes["action"], UpstreamCompletionAction)


def test_node_spec_foundry_completion_type(mock_settings) -> None:
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="foundry_completion")},
        gates=GateConfig(max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    from agentic_sdk.workflow.nodes.action import FoundryCompletionAction
    assert isinstance(wf.nodes["action"], FoundryCompletionAction)


# ── 自訂節點 import path ──────────────────────────────────────────────────────

def test_custom_node_import_path_not_found_raises(mock_settings) -> None:
    config = WorkflowConfig(
        nodes={"action": NodeSpec(type="nonexistent.module.SomeNode")},
        gates=GateConfig(max_revisit=3, timeout_sec=5.0),
    )
    with pytest.raises(ImportError, match="nonexistent"):
        Workflow.from_config(config, settings=mock_settings)


# ── M5-1:Plan system_prompt 模板參數 ──────────────────────────────────────────

class _StubFoundry:
    """攔截 chat() 呼叫,記錄傳入的 system prompt 供斷言。"""

    label = "stub-foundry"

    def __init__(self) -> None:
        self.last_system: str | None = None

    def chat(self, *, system: str, user: str, temperature: float = 0.0):
        from agentic_sdk.workflow.llm import FoundryResponse
        self.last_system = system
        return FoundryResponse(
            content='{"thought": "stub", "next_node": "action"}',
            model="stub-model",
            input_tokens=1,
            output_tokens=1,
        )


def _make_plan_state(message: str = "hi"):
    from agentic_sdk.workflow.node import WorkflowState
    return WorkflowState(user_message=message)


def test_plan_uses_react_template_by_default() -> None:
    from agentic_sdk.workflow.nodes.plan.react import ReActPlan, SYSTEM_PROMPT_TEMPLATES

    stub = _StubFoundry()
    plan = ReActPlan(foundry_client=stub)
    plan(_make_plan_state())

    assert stub.last_system == SYSTEM_PROMPT_TEMPLATES["react"]


def test_plan_accepts_custom_system_prompt() -> None:
    from agentic_sdk.workflow.nodes.plan.react import ReActPlan

    stub = _StubFoundry()
    custom = "PLAN. 自訂規劃指示:永遠選 action。只回 JSON。"
    plan = ReActPlan(foundry_client=stub, system_prompt=custom)
    plan(_make_plan_state())

    assert stub.last_system == custom


def test_plan_built_via_workflow_config_passes_system_prompt(mock_settings) -> None:
    """確認 WorkflowConfig.params["system_prompt"] 能透過 from_config 流入 Plan。"""
    from agentic_sdk.workflow.nodes.plan.react import ReActPlan

    custom = "PLAN. CoT 變體。"
    config = WorkflowConfig(
        nodes={
            "plan": NodeSpec(type="builtin.plan", params={"system_prompt": custom}),
            "action": NodeSpec(type="foundry_completion"),
        },
        gates=GateConfig(max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    plan_node = wf.nodes["plan"]
    assert isinstance(plan_node, ReActPlan)
    assert plan_node._system_prompt == custom


# ── M5-1:Reflect on_failure 參數 ─────────────────────────────────────────────

def _make_reflect_state_with_error():
    state = _make_plan_state()
    state.last_action_error = {"message": "boom"}
    return state


def _make_reflect_state_ok():
    return _make_plan_state()


def test_reflect_default_on_failure_routes_to_plan() -> None:
    from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect

    reflect = RuleBasedReflect()
    out = reflect(_make_reflect_state_with_error())
    assert out["next_node"] == "plan"


def test_reflect_on_failure_end_routes_to_none() -> None:
    from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect

    reflect = RuleBasedReflect(on_failure="end")
    out = reflect(_make_reflect_state_with_error())
    assert out["next_node"] is None


def test_reflect_pass_path_always_ends_regardless_of_on_failure() -> None:
    from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect

    for mode in ("retry_plan", "end"):
        reflect = RuleBasedReflect(on_failure=mode)
        out = reflect(_make_reflect_state_ok())
        assert out["next_node"] is None, f"on_failure={mode} 在無錯時應回 None"


def test_reflect_invalid_on_failure_raises() -> None:
    from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect

    with pytest.raises(ValueError, match="on_failure"):
        RuleBasedReflect(on_failure="restart_workflow")


def test_reflect_built_via_workflow_config_passes_on_failure(mock_settings) -> None:
    """確認 WorkflowConfig.params["on_failure"] 能透過 from_config 流入 Reflect。"""
    from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect

    config = WorkflowConfig(
        nodes={
            "reflect": NodeSpec(type="builtin.reflect", params={"on_failure": "end"}),
            "action": NodeSpec(type="foundry_completion"),
        },
        gates=GateConfig(max_revisit=3, timeout_sec=10.0),
    )
    wf = Workflow.from_config(config, settings=mock_settings)
    reflect_node = wf.nodes["reflect"]
    assert isinstance(reflect_node, RuleBasedReflect)
    assert reflect_node._on_failure == "end"

