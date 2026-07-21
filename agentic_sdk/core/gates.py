from __future__ import annotations

import time
from dataclasses import dataclass

from agentic_sdk.core.module import WorkflowAborted, WorkflowState


@dataclass
class Gates:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0

    def before_visit(self, module_name: str, state: WorkflowState, total_hops: int) -> None:
        if total_hops > self.max_node_hops:
            raise WorkflowAborted(f"total module hops {total_hops} exceeded {self.max_node_hops}")
        if state.visit_counts.get(module_name, 0) >= self.max_revisit:
            raise WorkflowAborted(f"module '{module_name}' exceeded revisit limit {self.max_revisit}")
        elapsed = time.monotonic() - state.started_monotonic
        if elapsed > self.timeout_sec:
            raise WorkflowAborted(f"workflow timeout after {elapsed:.2f}s")