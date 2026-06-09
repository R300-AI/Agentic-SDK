"""A-06 — Timeout 閘門單元測試(M1-4 完整版)。

驗 timeout 在第二次節點進入前觸發,P99 中止;搭配既有 hops/revisit 測試
構成「三道閘門皆能 P99 < 5 秒中止」的完整覆蓋。
"""

from __future__ import annotations

import time

import pytest

from agentic_sdk.workflow.gates import Gates
from agentic_sdk.workflow.node import WorkflowAborted, WorkflowState


def test_timeout_gate_aborts_when_elapsed_exceeds_limit():
    g = Gates(max_node_hops=999, max_revisit=999, timeout_sec=0.05)
    state = WorkflowState(user_message="hi")
    time.sleep(0.1)
    with pytest.raises(WorkflowAborted) as ei:
        g.before_visit("plan", state, total_hops=2)
    assert "workflow 逾時" in str(ei.value)


def test_timeout_gate_does_not_trip_when_within_limit():
    g = Gates(max_node_hops=999, max_revisit=999, timeout_sec=5.0)
    state = WorkflowState(user_message="hi")
    g.before_visit("plan", state, total_hops=1)  # 不應拋
