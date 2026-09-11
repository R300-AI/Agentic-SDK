from __future__ import annotations

import time
from dataclasses import dataclass

from agentic_sdk.core.module import WorkflowAborted, WorkflowState


_BOUNDED_BY_OTHER_LIMITS = {"plan", "reflect"}


@dataclass
class Gates:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0
    # How many times planning may send work to reflect in one run. Unlike the
    # other limits, reaching it does not abort: reflect simply stops being one
    # of planning's choices, and the run carries on to retrieve or act.
    max_reflect_rounds: int = 5

    def before_visit(self, module_name: str, state: WorkflowState, total_hops: int) -> None:
        if total_hops > self.max_node_hops:
            raise WorkflowAborted(f"total module hops {total_hops} exceeded {self.max_node_hops}")
        # Planning is visited once more after every retrieval and every reflect,
        # so its count is already bounded by theirs; reflect has a limit of its
        # own, which narrows planning's choices instead of aborting. Holding
        # either to max_revisit would abort a run before those limits were reached.
        if module_name not in _BOUNDED_BY_OTHER_LIMITS and state.visit_counts.get(module_name, 0) >= self.max_revisit:
            raise WorkflowAborted(f"module '{module_name}' exceeded revisit limit {self.max_revisit}")
        elapsed = time.monotonic() - state.started_monotonic
        if elapsed > self.timeout_sec:
            raise WorkflowAborted(f"workflow timeout after {elapsed:.2f}s")