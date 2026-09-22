from __future__ import annotations

from agentic_sdk.core import ModuleOutput, WorkflowState
from agentic_sdk.modules.retrieve.base import BaseRetrieve


class PassThroughRetrieve(BaseRetrieve):
    produced_by = "pass_through_retrieve"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = str(state.lookup("perceived_input") or state.lookup("query") or state.latest_user_message()).strip()
        return self._retrieved(content, items=[])
