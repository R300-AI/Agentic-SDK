from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_sdk.core import Gates, Module, Workflow
from agentic_sdk.core.events import resolve_events_schema
from agentic_sdk.memory import FileMemoryStore, InContextMemory, InMemoryStore, MemoryStore


@dataclass
class GateConfig:
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0
    max_reflect_rounds: int = 5
    max_prompt_tokens: int | None = None


@dataclass
class ModuleSpec:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemorySpec:
    """Which memory a workflow keeps, and how it is set up.

    Same shape as a module — a kind and its settings — because that is a shape
    whoever writes one of these already knows. It is not a module: memory has
    no slot in the walk, it is what every module reads from and writes to, so
    it gets its own field rather than a sixth entry among the five.

    The kind names what the memory does, never what it writes to. A deployment
    that moves from files to something else changes what it passes in ``root``;
    a spec somebody saved a year ago still says ``cross_context``.
    """

    kind: str = "in_context"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowConfig:
    name: str = "default"
    description: str | None = None
    entry: str = "perceive"
    events_schema: dict[str, dict[str, Any]] | None = None
    gates: GateConfig = field(default_factory=GateConfig)
    memory: MemorySpec = field(default_factory=MemorySpec)
    modules: dict[str, ModuleSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.events_schema = resolve_events_schema(self.events_schema)


# What each kind of memory can be set up with. The endpoint three are here
# because collecting old exchanges into a topic is a model call of its own,
# and a deployment may point it at a smaller endpoint than the answer uses.
_MEMORY_CONFIG_PARAMS: dict[str, set[str]] = {
    "in_context": set(),
    "cross_context": {
        "root",
        "api_key",
        "base_url",
        "model",
        "compaction_threshold_tokens",
        "raw_retention_seconds",
    },
}


_MODULE_CONFIG_PARAMS: dict[str, set[str]] = {
    "direct_answer": {"memory_key", "fallback", "prefix"},
    "evidence_check": set(),
    "generative": {"api_key", "base_url", "model", "temperature", "system_prompt"},
    "keyword": {"items", "fallback"},
    "next_step": {"api_key", "base_url", "model", "system_prompt", "retrieve_description", "reflect_description"},
    "pass_through": {"input_label"},
    "pass_through_plan": set(),
    "pass_through_retrieve": set(),
    "plan_check": {"api_key", "base_url", "model"},
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
    # The transport is an object, like semantic retrieve's embedder: an audio
    # source cannot be described by settings, so a spec that names a voice
    # module is completed by whoever builds it. See ADR-0003.
    "voice_text": {
        "transport",
        "speech_threshold",
        "hangover_seconds",
    },
    "voice_answer": {
        "api_key",
        "base_url",
        "model",
        "temperature",
        "system_prompt",
        "speech",
    },
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
            max_reflect_rounds=config.gates.max_reflect_rounds,
            max_prompt_tokens=config.gates.max_prompt_tokens,
        ),
        memory_type=build_memory(config.memory),
        workflow_name=config.name,
        description=config.description,
        entry_module=config.entry,
        events_schema=config.events_schema,
    )


def build_memory(spec: MemorySpec) -> MemoryStore | type[MemoryStore]:
    """Build the memory a config declares.

    Carrying nothing between conversations needs nothing set up, so that kind
    is handed back as the class and a fresh one is made per run. Carrying
    things between conversations is set up here, once, because where it keeps
    them and which endpoint collects them are settings somebody supplied.

    Where it keeps them decides which implementation runs. Told a place, it
    writes there and what it learnt outlives the process. Told nothing, it
    keeps everything in memory — a deployment that has said nothing about
    storage still gets a workflow that starts, and it loses what it learnt
    when the process ends. See ADR-0017.
    """
    if spec.kind not in _MEMORY_CONFIG_PARAMS:
        known = ", ".join(sorted(_MEMORY_CONFIG_PARAMS))
        raise ValueError(f"unknown memory kind {spec.kind!r}. Allowed kinds: {known}")
    unsupported = sorted(set(spec.params) - _MEMORY_CONFIG_PARAMS[spec.kind])
    if unsupported:
        allowed = ", ".join(sorted(_MEMORY_CONFIG_PARAMS[spec.kind])) or "none"
        raise ValueError(f"unsupported params for memory kind {spec.kind!r}: {unsupported}. Allowed params: {allowed}")
    if spec.kind == "in_context":
        return InContextMemory
    params = dict(spec.params)
    root = params.pop("root", None)
    if root:
        return FileMemoryStore(root=str(root), **params)
    # Nothing is written, so nothing set up for writing applies: how long raw
    # records are kept is about files on disk, and collecting them is about
    # what a long conversation costs to hand over — neither survives a restart
    # here anyway. Dropping them beats refusing a config that named them.
    return InMemoryStore()


def build_module(spec: ModuleSpec) -> Module:
    from agentic_sdk import modules

    registry = {
        "direct_answer": modules.DirectAnswerAction,
        "evidence_check": modules.EvidenceCheckReflect,
        "generative": modules.GenerativeAction,
        "keyword": modules.KeywordRetrieve,
        "next_step": modules.NextStepPlan,
        "pass_through": modules.PassThroughPerceive,
        "pass_through_plan": modules.PassThroughPlan,
        "pass_through_retrieve": modules.PassThroughRetrieve,
        "plan_check": modules.PlanCheckReflect,
        "semantic": modules.SemanticRetrieve,
        "text": modules.TextPerceive,
        "text_image": modules.TextImagePerceive,
        "tool_call_action": modules.ToolCallAction,
        "voice_answer": modules.VoiceAnswerAction,
        "voice_text": modules.VoiceTextPerceive,
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