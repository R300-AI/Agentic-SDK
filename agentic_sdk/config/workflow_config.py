from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_sdk.core import Gates, Module, Workflow


@dataclass
class GateConfig:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0


@dataclass
class ModuleSpec:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowConfig:
    name: str = "default"
    description: str | None = None
    entry: str = "perceive"
    gates: GateConfig = field(default_factory=GateConfig)
    modules: dict[str, ModuleSpec] = field(default_factory=dict)


_MODULE_CONFIG_PARAMS: dict[str, set[str]] = {
    "direct_answer": {"memory_key", "fallback", "prefix"},
    "evidence_check": {"on_failure"},
    "generative": {"api_key", "base_url", "model", "temperature", "system_prompt"},
    "keyword": {"items", "fallback"},
    "next_step": {"api_key", "base_url", "model", "system_prompt", "retrieve_description"},
    "pass_through": {"input_label"},
    "pass_through_retrieve": set(),
    "response_check": {"on_failure", "api_key", "base_url", "model"},
    "semantic": {
        "top_k",
        "provider",
        "api_key",
        "base_url",
        "embedding_model",
        "sources",
        "saved_path",
        "index_path",
        "source_path",
        "rebuild_if_missing",
        "rebuild_if_stale",
        "chunk_size",
        "chunk_overlap",
        "embedder",
        "knowledge_base",
        "vision_query",
    },
    "text": {"welcome_message", "options", "importance", "api_key", "base_url", "model"},
    "text_image": {
        "welcome_message",
        "options",
        "importance",
        "image_instruction",
        "api_key",
        "base_url",
        "model",
    },
    "tool_call_action": {"api_key", "base_url", "model", "temperature", "system_prompt", "tools", "tool_choice"},
}


def build_workflow(config: WorkflowConfig, *, module_overrides: dict[str, Module] | None = None) -> Workflow:
    overrides = module_overrides or {}

    def module_for(name: str) -> Module | None:
        if name in overrides:
            return overrides[name]
        spec = config.modules.get(name)
        if spec is None:
            return None
        return build_module(spec)

    return Workflow(
        perceive=module_for("perceive"),
        plan=module_for("plan"),
        retrieve=module_for("retrieve"),
        action=module_for("action"),
        reflect=module_for("reflect"),
        gates=Gates(
            max_node_hops=config.gates.max_node_hops,
            max_revisit=config.gates.max_revisit,
            timeout_sec=config.gates.timeout_sec,
        ),
        workflow_name=config.name,
        description=config.description,
        entry_module=config.entry,
    )


def build_module(spec: ModuleSpec) -> Module:
    from agentic_sdk import modules

    registry = {
        "direct_answer": modules.DirectAnswerAction,
        "evidence_check": modules.EvidenceCheckReflect,
        "generative": modules.GenerativeAction,
        "keyword": modules.KeywordRetrieve,
        "next_step": modules.NextStepPlan,
        "pass_through": modules.PassThroughPerceive,
        "pass_through_retrieve": modules.PassThroughRetrieve,
        "response_check": modules.ResponseCheckReflect,
        "semantic": modules.SemanticRetrieve,
        "text": modules.TextPerceive,
        "text_image": modules.TextImagePerceive,
        "tool_call_action": modules.ToolCallAction,
    }
    try:
        constructor = registry[spec.kind]
    except KeyError as exc:
        raise ValueError(f"unknown module kind {spec.kind!r}") from exc
    unsupported = sorted(set(spec.params) - _MODULE_CONFIG_PARAMS[spec.kind])
    if unsupported:
        allowed = ", ".join(sorted(_MODULE_CONFIG_PARAMS[spec.kind])) or "none"
        raise ValueError(f"unsupported params for module kind {spec.kind!r}: {unsupported}. Allowed params: {allowed}")
    return constructor(**spec.params)