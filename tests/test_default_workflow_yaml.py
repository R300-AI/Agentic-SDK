"""M5-3 — examples/workflows/default.yaml 與 editor 預設 YAML 同步驗證。

editor 端 src/defaultWorkflow.ts 的 DEFAULT_WORKFLOW_YAML 與此檔必須完全等價,
保證使用者下載的 YAML 可被 SDK 載入並跑通。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_sdk.workflow import Workflow, WorkflowConfig

DEFAULT_YAML_PATH = Path(__file__).parent.parent / "examples" / "workflows" / "default.yaml"


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


def test_default_yaml_file_exists() -> None:
    assert DEFAULT_YAML_PATH.is_file(), f"預設工作流 YAML 不存在:{DEFAULT_YAML_PATH}"


def test_default_yaml_loads_to_valid_config() -> None:
    config = WorkflowConfig.from_yaml(DEFAULT_YAML_PATH)
    assert config.version == "1"
    assert config.entry == "perceive"
    assert set(config.nodes.keys()) == {"perceive", "plan", "retrieve", "reflect", "action"}
    assert config.nodes["action"].type == "foundry_completion"
    assert config.nodes["reflect"].params == {"on_failure": "retry_plan"}
    assert config.gates.max_node_hops == 20
    assert config.gates.max_revisit == 3
    assert config.gates.timeout_sec == 30.0


def test_default_yaml_roundtrip_stable() -> None:
    """載入 → 序列化 → 再載入,結果必須完全一致(等同 editor 的「下載→載入」循環)。"""
    config_a = WorkflowConfig.from_yaml(DEFAULT_YAML_PATH)
    yaml_text = config_a.to_yaml()
    config_b = WorkflowConfig.from_yaml(yaml_text)
    assert config_a.to_dict() == config_b.to_dict()


def test_default_yaml_runs_to_completion(mock_settings) -> None:
    """預設 YAML 直接餵 Workflow.from_config 就能跑通,證明 editor 預設 ready-to-run。"""
    from unittest.mock import MagicMock
    from agentic_sdk.workflow.nodes.action import FoundryCompletionAction

    fake_message = MagicMock(content="預設 YAML 跑通的回應")
    fake_choice = MagicMock(message=fake_message)
    fake_completion = MagicMock(choices=[fake_choice], usage=None, model="mock-deployment")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion

    config = WorkflowConfig.from_yaml(DEFAULT_YAML_PATH)
    action = FoundryCompletionAction(settings=mock_settings, client=fake_client)
    wf = Workflow.from_config(config, settings=mock_settings, node_overrides={"action": action})
    result = wf.run("hello")

    assert not result.aborted
    assert result.final_message == "預設 YAML 跑通的回應"
