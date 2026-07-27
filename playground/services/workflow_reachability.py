from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playground.services.source_builder import BuilderSourceConfig


_MODEL_PERCEIVE_MODULES = {"TextPerceive", "TextImagePerceive"}
_MODEL_ACTION_MODULES = {"GenerativeAction", "ToolCallAction"}


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
    if "plan" in reachable and config.plan_strategy:
        roles.add("plan")
    if "action" in reachable and config.action_module in _MODEL_ACTION_MODULES:
        roles.add("action")
    if "reflect" in reachable and config.reflect_module == "ResponseCheckReflect":
        roles.add("reflect")
    return roles


def _next_roles(config: "BuilderSourceConfig", role: str) -> tuple[str, ...]:
    if role == "perceive":
        return ("plan",) if config.plan_strategy else ("retrieve",)
    if role == "plan":
        return ("retrieve", "action") if config.plan_strategy else ()
    if role == "retrieve":
        return ("action",)
    if role == "action":
        return ("reflect",) if config.reflect_module else ()
    if role == "reflect" and config.reflect_on_failure == "retry_plan" and config.plan_strategy:
        return ("plan",)
    return ()