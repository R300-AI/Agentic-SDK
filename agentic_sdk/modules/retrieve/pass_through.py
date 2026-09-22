from __future__ import annotations

from agentic_sdk.core import ModuleOutput, WorkflowState
from agentic_sdk.modules.retrieve.base import BaseRetrieve


class PassThroughRetrieve(BaseRetrieve):
    produced_by = "pass_through_retrieve"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = str(state.lookup("perceived_input") or state.lookup("query") or state.latest_user_message()).strip()
        sections, remembered = self._with_memory([content] if content else [], state, content)
        return self._retrieved(
            "\n\n".join(sections),
            items=[],
            # A module that looked nothing up reports no hit_count and gets
            # no verdict from reflect; one that reached memory did look
            # something up, and says so.
            metadata={"memory_hit_count": remembered, "hit_count": remembered}
            if remembered
            else {"memory_hit_count": 0},
        )
