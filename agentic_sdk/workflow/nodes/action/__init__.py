from agentic_sdk.workflow.nodes.action.foundry_completion import FoundryCompletionAction
from agentic_sdk.workflow.nodes.action.upstream_completion import UpstreamCompletionAction

DEFAULT = UpstreamCompletionAction

__all__ = ["FoundryCompletionAction", "UpstreamCompletionAction", "DEFAULT"]
