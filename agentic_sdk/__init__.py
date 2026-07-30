"""Clean core package for Agentic SDK v2."""

__version__ = "0.1.0"

from agentic_sdk.config import GateConfig, ModuleSpec, WorkflowConfig, build_workflow
from agentic_sdk.defaults import (
    DEFAULT_NO_MATCHING_ENTRIES_MESSAGE,
    DEFAULT_NO_RETRIEVED_CONTEXT_MESSAGE,
    DEFAULT_RETRIEVED_CONTENT_KEY,
    DEFAULT_SESSION_ID,
    DEFAULT_WORKFLOW_NAME,
    SEMANTIC_RETRIEVE_DEFAULT_INDEX_DIRNAME,
    SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH,
    SEMANTIC_RETRIEVE_DEFAULT_SOURCE_DIRNAME,
    SEMANTIC_RETRIEVE_DEFAULT_TOP_K,
)
from agentic_sdk.core import (
    Attachment,
    ConversationTurn,
    ContextEntry,
    ContextEntryType,
    Entities,
    Gates,
    InContextMemory,
    Module,
    ModuleOutput,
    Workflow,
    WorkflowAborted,
    WorkflowResult,
    WorkflowState,
)
from agentic_sdk.memory import InMemoryStore, MemoryEntry, MemorySearchResult, MemoryStore, PersistentMemory

_LAZY_MODULE_EXPORTS = {
    "DirectAnswerAction": "agentic_sdk.modules.action",
    "EvidenceCheckReflect": "agentic_sdk.modules.reflect",
    "GenerativeAction": "agentic_sdk.modules.action",
    "KeywordRetrieve": "agentic_sdk.modules.retrieve",
    "NextStepPlan": "agentic_sdk.modules.plan",
    "PassThroughPerceive": "agentic_sdk.modules.perceive",
    "PassThroughRetrieve": "agentic_sdk.modules.retrieve",
    "ResponseCheckReflect": "agentic_sdk.modules.reflect",
    "SemanticRetrieve": "agentic_sdk.modules.retrieve",
    "TextImagePerceive": "agentic_sdk.modules.perceive",
    "TextPerceive": "agentic_sdk.modules.perceive",
    "ToolCallAction": "agentic_sdk.modules.action",
}


def __getattr__(name: str):
    module_name = _LAZY_MODULE_EXPORTS.get(name)
    if not module_name:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

__all__ = [
    "Attachment",
    "ConversationTurn",
    "ContextEntry",
    "ContextEntryType",
    "DirectAnswerAction",
    "DEFAULT_NO_MATCHING_ENTRIES_MESSAGE",
    "DEFAULT_NO_RETRIEVED_CONTEXT_MESSAGE",
    "DEFAULT_RETRIEVED_CONTENT_KEY",
    "DEFAULT_SESSION_ID",
    "DEFAULT_WORKFLOW_NAME",
    "Entities",
    "EvidenceCheckReflect",
    "GateConfig",
    "Gates",
    "GenerativeAction",
    "InContextMemory",
    "InMemoryStore",
    "KeywordRetrieve",
    "MemoryEntry",
    "MemorySearchResult",
    "MemoryStore",
    "PersistentMemory",
    "Module",
    "ModuleOutput",
    "ModuleSpec",
    "NextStepPlan",
    "PassThroughPerceive",
    "PassThroughRetrieve",
    "ResponseCheckReflect",
    "SEMANTIC_RETRIEVE_DEFAULT_INDEX_DIRNAME",
    "SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH",
    "SEMANTIC_RETRIEVE_DEFAULT_SOURCE_DIRNAME",
    "SEMANTIC_RETRIEVE_DEFAULT_TOP_K",
    "SemanticRetrieve",
    "TextImagePerceive",
    "TextPerceive",
    "ToolCallAction",
    "Workflow",
    "WorkflowAborted",
    "WorkflowConfig",
    "WorkflowResult",
    "WorkflowState",
    "build_workflow",
    "__version__",
]