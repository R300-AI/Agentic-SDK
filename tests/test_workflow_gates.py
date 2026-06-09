"""A-01 — Gates(MAX_NODE_HOPS / MAX_REVISIT)觸發驗證。"""

from __future__ import annotations

import pytest

from agentic_sdk.workflow.gates import Gates
from agentic_sdk.workflow.node import WorkflowAborted, WorkflowState


def test_max_hops_triggers_abort():
    gates = Gates(max_node_hops=3, max_revisit=10)
    state = WorkflowState(user_message="x")
    # 前三跳通過
    for hop in (1, 2, 3):
        gates.before_visit("any", state, hop)
    with pytest.raises(WorkflowAborted, match="total node hops"):
        gates.before_visit("any", state, 4)


def test_max_revisit_triggers_abort():
    gates = Gates(max_node_hops=100, max_revisit=2)
    state = WorkflowState(user_message="x")
    gates.before_visit("plan", state, 1)
    state.increment_visit("plan")
    gates.before_visit("plan", state, 2)
    state.increment_visit("plan")
    with pytest.raises(WorkflowAborted, match="重訪次數"):
        gates.before_visit("plan", state, 3)


def test_gates_independent_per_node():
    gates = Gates(max_node_hops=100, max_revisit=2)
    state = WorkflowState(user_message="x")
    state.visit_counts = {"plan": 1, "retrieve": 1}
    # 兩個節點各自只用了 1 次,都還能進
    gates.before_visit("plan", state, 5)
    gates.before_visit("retrieve", state, 5)
