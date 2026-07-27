from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModeContext:
    mode: str = "anonymous"
    label: str = "Anonymous trial"
    role: str = "creator"
    can_save: bool = False
    can_edit: bool = True
    can_export: bool = False
    can_view_code: bool = False
    is_aihub: bool = False
    source_origin: str = "local"
    source_label: str = "New local workflow"


@dataclass(frozen=True)
class BuilderChoice:
    label: str
    title: str
    description: str
    available: bool = True
    badge: str = ""


@dataclass(frozen=True)
class BuilderStep:
    key: str
    title: str
    subtitle: str
    technical_name: str
    prompt: str
    choices: tuple[BuilderChoice, ...] = field(default_factory=tuple)
    completed: bool = False
    blocked: bool = False
    control: str = "choices"


@dataclass(frozen=True)
class RunnerSceneProfile:
    layout_variant: str = "chat_first"
    primary_input_kind: str = "chat"
    primary_result_kind: str = "message"
    task_archetype: str = "consultant"
    enabled_slots: list[str] = field(default_factory=lambda: ["conversation", "result_summary", "evidence"])
    layout_fit: dict[str, str] = field(
        default_factory=lambda: {
            "chat_first": "preferred",
            "form_first": "fallback",
            "result_first": "supported",
        }
    )


@dataclass(frozen=True)
class WorkflowSummary:
    name: str
    input_contract: str
    output_contract: str
    template: str
    readiness: str
    can_run: bool
    can_roundtrip: bool