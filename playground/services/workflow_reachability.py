from __future__ import annotations

from typing import TYPE_CHECKING
MODEL_PLANNING_MODULES = {"NextStepPlan", "NextStepWithSkills"}
"""The planning modules that ask a model, and so need an endpoint bound to plan."""

if TYPE_CHECKING:
    from playground.services.source_builder import BuilderSourceConfig


_MODEL_PERCEIVE_MODULES = {"TextPerceive", "TextImagePerceive"}
_MODEL_ACTION_MODULES = {"GenerativeAction", "ToolCallAction", "VoiceAnswerAction"}


def reachable_workflow_roles(config: "BuilderSourceConfig") -> set[str]:
    pending = [config.entry_module or "perceive"]
    reachable: set[str] = set()
    while pending:
        role = pending.pop(0)
        if role in reachable:
            continue
        reachable.add(role)
        for next_role in _next_roles(config, role):
            if next_role not in reachable:
                pending.append(next_role)
    return reachable


def reachable_openai_roles(config: "BuilderSourceConfig") -> set[str]:
    reachable = reachable_workflow_roles(config)
    roles: set[str] = set()
    if "perceive" in reachable and config.perceive_module in _MODEL_PERCEIVE_MODULES:
        roles.add("perceive")
    if "plan" in reachable and config.plan_module in MODEL_PLANNING_MODULES:
        roles.add("plan")
    if "action" in reachable and config.action_module in _MODEL_ACTION_MODULES:
        roles.add("action")
    if "reflect" in reachable and config.reflect_module == "PlanCheckReflect":
        roles.add("reflect")
    return roles


def _next_roles(config: "BuilderSourceConfig", role: str) -> tuple[str, ...]:
    # Planning chooses; everything it sends work to hands back to it, and the
    # action ends the run — see ADR-0005.
    if role == "plan":
        return ("retrieve", "reflect", "action") if config.reflect_module else ("retrieve", "action")
    if role in {"perceive", "retrieve", "reflect"}:
        return ("plan",)
    return ()
