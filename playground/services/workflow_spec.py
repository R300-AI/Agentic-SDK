"""v2 Workflow Spec – single source of truth for Builder state.

Spec is stored as JSON in the database; Python source is compiled from spec
and is treated as a read-only export, never parsed back.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from playground.services.source_builder import (
    BuilderSourceConfig,
    _build_source_for_config,
    _tools_from_action_payload,
    _payload_has_interactive_contract,
    _action_prompt_from_payload,
    _fixed_format_action_prompt_from_payload,
    _option_items_from_pairs,
    _string_items_from_lines,
    _retrieve_items_from_payload,
    _pairs_text_from_retrieve_items,
    _pairs_text_from_options,
    _lines_text_from_items,
    _response_instruction_from_prompt,
    _api_contracts_json_from_tools,
    _clean_prompt,
    _clean_short_text,
    _clean_allowed_value,
    _clean_workflow_name,
    _ALLOWED_DIRECT_RESULT_KEYS,
    _INTERACTIVE_TOOL_POLICY,
    _ALLOWED_ENTRY_MODULES,
    _FREE_TEXT_OUTPUT_CHOICES,
    _INTERACTIVE_OUTPUT_CHOICES,
    _TOOL_CALL_OUTPUT_CHOICES,
    _STRUCTURED_OUTPUT_CHOICES,
    _DEFAULT_WORKFLOW_NAME,
    _GENERATED_WORKFLOW_NAMES,
    DEFAULT_RETRIEVED_CONTENT_KEY,
)

_SPEC_VERSION = "2"
_PRESENTATION_VERSION = "1"

_ALLOWED_MEMORY_KINDS = {"in_context"}
_ALLOWED_PERCEIVE_MODULES = {"PassThroughPerceive", "TextPerceive", "TextImagePerceive"}
_ALLOWED_RETRIEVE_MODULES = {"PassThroughRetrieve", "KeywordRetrieve", "SemanticRetrieve"}
_ALLOWED_ACTION_MODULES = {"DirectAnswerAction", "GenerativeAction", "ToolCallAction"}
_ALLOWED_REFLECT_MODULES = {"EvidenceCheckReflect", "ResponseCheckReflect"}
_ALLOWED_REFLECT_ON_FAILURE = {"retry_plan", "end"}
_ALLOWED_PLAN_STRATEGIES = {"RouteBySupport"}


# ---------------------------------------------------------------------------
# Default spec
# ---------------------------------------------------------------------------

def default_spec(*, workflow_name: str = _DEFAULT_WORKFLOW_NAME) -> dict[str, Any]:
    return {
        "version": _SPEC_VERSION,
        "workflow_name": workflow_name,
        "description": "",
        "memory": {"kind": "in_context"},
        "perceive": {
            "module": "PassThroughPerceive",
            "params": {
                "input_label": None,
                "welcome_message": None,
                "options": [],
                "importance": 1.0,
                "image_instruction": None,
            },
        },
        "retrieve": {
            "module": "PassThroughRetrieve",
            "params": {
                "description": None,
                "items": [],
                "fallback": "沒有命中任何條目。",
                "top_k": 3,
                "support_files": [],
                "search_goal": None,
            },
        },
        "plan": {
            "module": None,
            "params": {"strategy": None, "system_prompt": None},
        },
        "action": {
            "module": "DirectAnswerAction",
            "params": {
                "output_format": "free_text",
                "system_prompt": None,
                "tools": [],
                "tool_choice": None,
                "memory_key": DEFAULT_RETRIEVED_CONTENT_KEY,
                "fallback": "沒有命中任何條目。",
                "prefix": "",
            },
        },
        "reflect": {
            "module": None,
            "params": {"on_failure": None},
        },
        "gates": {"max_node_hops": 50, "max_revisit": 5, "timeout_sec": 300.0},
        "events": None,
        "entry_module": "perceive",
    }


def default_runner_presentation() -> dict[str, Any]:
    return {"version": _PRESENTATION_VERSION, "starter_questions": []}


# ---------------------------------------------------------------------------
# Validation / normalisation
# ---------------------------------------------------------------------------

def validate_spec(raw: object) -> dict[str, Any]:
    """Return a clean, fully-populated spec dict or raise ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("workflow_spec must be a JSON object")
    spec = default_spec()
    _apply_str_field(spec, raw, "workflow_name", required=False)
    _apply_str_field(spec, raw, "description", required=False)
    _apply_memory(spec, raw.get("memory"))
    _apply_perceive(spec, raw.get("perceive"))
    _apply_retrieve(spec, raw.get("retrieve"))
    _apply_plan(spec, raw.get("plan"))
    _apply_action(spec, raw.get("action"))
    _apply_reflect(spec, raw.get("reflect"))
    _apply_gates(spec, raw.get("gates"))
    if "events" in raw and isinstance(raw["events"], (dict, type(None))):
        spec["events"] = raw["events"]
    if "entry_module" in raw:
        entry = str(raw["entry_module"] or "perceive")
        spec["entry_module"] = entry if entry in _ALLOWED_ENTRY_MODULES else "perceive"
    spec["version"] = _SPEC_VERSION
    return spec


def validate_runner_presentation(raw: object) -> dict[str, Any]:
    pres = default_runner_presentation()
    if not isinstance(raw, dict):
        return pres
    raw_qs = raw.get("starter_questions")
    if isinstance(raw_qs, list):
        pres["starter_questions"] = [str(q) for q in raw_qs if isinstance(q, str) and q.strip()][:20]
    return pres


def _apply_str_field(spec: dict, raw: dict, key: str, *, required: bool = True) -> None:
    if key in raw:
        spec[key] = str(raw[key] or "").strip()
    elif required:
        raise ValueError(f"Missing required field: {key}")


def _apply_memory(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    kind = str(raw.get("kind") or "in_context")
    spec["memory"]["kind"] = kind if kind in _ALLOWED_MEMORY_KINDS else "in_context"


def _apply_perceive(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = str(raw.get("module") or "PassThroughPerceive")
    if module not in _ALLOWED_PERCEIVE_MODULES:
        module = "PassThroughPerceive"
    spec["perceive"]["module"] = module
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    params = spec["perceive"]["params"]
    if "input_label" in p:
        params["input_label"] = _clean_short_text(str(p["input_label"] or ""), "") or None
    if "welcome_message" in p:
        params["welcome_message"] = _clean_prompt(str(p["welcome_message"] or "")) or None
    if "options" in p and isinstance(p["options"], list):
        params["options"] = [o for o in p["options"] if isinstance(o, dict) and o.get("label") and o.get("intent")][:20]
    if "importance" in p:
        params["importance"] = max(0.0, min(5.0, float(p["importance"] or 1.0)))
    if "image_instruction" in p:
        params["image_instruction"] = _clean_prompt(str(p["image_instruction"] or "")) or None


def _apply_retrieve(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = str(raw.get("module") or "PassThroughRetrieve")
    if module not in _ALLOWED_RETRIEVE_MODULES:
        module = "PassThroughRetrieve"
    spec["retrieve"]["module"] = module
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    params = spec["retrieve"]["params"]
    if "description" in p:
        params["description"] = _clean_prompt(str(p["description"] or "")) or None
    if "items" in p and isinstance(p["items"], list):
        params["items"] = [i for i in p["items"] if isinstance(i, dict)][:100]
    if "fallback" in p:
        params["fallback"] = _clean_short_text(str(p["fallback"] or ""), "沒有命中任何條目。")
    if "top_k" in p:
        params["top_k"] = max(1, min(20, int(p["top_k"] or 3)))
    if "support_files" in p and isinstance(p["support_files"], list):
        params["support_files"] = [str(f) for f in p["support_files"] if str(f).strip()][:50]
    if "search_goal" in p:
        params["search_goal"] = _clean_prompt(str(p["search_goal"] or "")) or None


def _apply_plan(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = raw.get("module")
    spec["plan"]["module"] = "NextStepPlan" if module else None
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    params = spec["plan"]["params"]
    if "strategy" in p:
        strategy = str(p["strategy"] or "")
        params["strategy"] = strategy if strategy in _ALLOWED_PLAN_STRATEGIES else None
    if "system_prompt" in p:
        params["system_prompt"] = _clean_prompt(str(p["system_prompt"] or "")) or None


def _apply_action(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = str(raw.get("module") or "DirectAnswerAction")
    if module not in _ALLOWED_ACTION_MODULES:
        module = "DirectAnswerAction"
    spec["action"]["module"] = module
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    params = spec["action"]["params"]
    if "output_format" in p:
        fmt = str(p["output_format"] or "free_text")
        params["output_format"] = fmt if fmt in (_FREE_TEXT_OUTPUT_CHOICES | _INTERACTIVE_OUTPUT_CHOICES) else "free_text"
    if "system_prompt" in p:
        params["system_prompt"] = _clean_prompt(str(p["system_prompt"] or "")) or None
    if "tools" in p and isinstance(p["tools"], list):
        params["tools"] = list(p["tools"])
    if "tool_choice" in p:
        params["tool_choice"] = p["tool_choice"]
    if "memory_key" in p:
        key = str(p["memory_key"] or DEFAULT_RETRIEVED_CONTENT_KEY)
        params["memory_key"] = key if key in _ALLOWED_DIRECT_RESULT_KEYS else DEFAULT_RETRIEVED_CONTENT_KEY
    if "fallback" in p:
        params["fallback"] = _clean_short_text(str(p["fallback"] or ""), "沒有命中任何條目。")
    if "prefix" in p:
        params["prefix"] = _clean_short_text(str(p["prefix"] or ""), "")


def _apply_reflect(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = raw.get("module")
    if module and module not in _ALLOWED_REFLECT_MODULES:
        module = None
    spec["reflect"]["module"] = module or None
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    if "on_failure" in p:
        on_failure = str(p["on_failure"] or "")
        spec["reflect"]["params"]["on_failure"] = on_failure if on_failure in _ALLOWED_REFLECT_ON_FAILURE else None


def _apply_gates(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    gates = spec["gates"]
    if "max_node_hops" in raw:
        gates["max_node_hops"] = max(1, min(500, int(raw["max_node_hops"] or 50)))
    if "max_revisit" in raw:
        gates["max_revisit"] = max(1, min(100, int(raw["max_revisit"] or 5)))
    if "timeout_sec" in raw:
        gates["timeout_sec"] = max(10.0, min(3600.0, float(raw["timeout_sec"] or 300.0)))


# ---------------------------------------------------------------------------
# Apply Builder step to spec
# ---------------------------------------------------------------------------

def apply_builder_step(spec: dict[str, Any], step_key: str, choice_label: object) -> dict[str, Any]:
    """Return a new spec with the given Builder step applied."""
    spec = dict(spec)  # shallow copy; deep sections are replaced as needed

    if step_key == "name":
        name = _clean_workflow_name(str(choice_label)) or spec.get("workflow_name") or _DEFAULT_WORKFLOW_NAME
        return {**spec, "workflow_name": name}

    if step_key == "description":
        desc = _clean_prompt(str(choice_label)) or ""
        return {**spec, "description": desc}

    if step_key == "memory_type":
        # memory_type step only concerns memory.kind – starter_questions go to runner_presentation
        if isinstance(choice_label, str):
            kind = choice_label if choice_label in _ALLOWED_MEMORY_KINDS else "in_context"
            return {**spec, "memory": {**spec.get("memory", {}), "kind": kind}}
        return spec

    if step_key == "input_type":
        choice = str(choice_label)
        overrides: dict[str, Any] = {}
        if choice == "pass_through":
            overrides = {
                "module": "PassThroughPerceive",
                "params": {**spec.get("perceive", {}).get("params", {}), "welcome_message": None, "options": [], "importance": 1.0, "image_instruction": None},
            }
        elif choice == "text":
            overrides = {
                "module": "TextPerceive",
                "params": {**spec.get("perceive", {}).get("params", {}), "importance": 1.0, "image_instruction": None},
            }
        elif choice == "text_image":
            overrides = {
                "module": "TextImagePerceive",
                "params": {**spec.get("perceive", {}).get("params", {}), "importance": 1.5},
            }
        if overrides:
            return {**spec, "perceive": {**spec.get("perceive", {}), **overrides}}
        return spec

    if step_key == "retrieve_policy":
        choice = str(choice_label)
        existing_plan = spec.get("plan", {})
        if choice == "none":
            return {
                **spec,
                "retrieve": {**spec.get("retrieve", {}), "module": "PassThroughRetrieve"},
                "plan": {"module": None, "params": {"strategy": None, "system_prompt": existing_plan.get("params", {}).get("system_prompt")}},
            }
        elif choice in ("keyword", "semantic"):
            retrieve_module = "KeywordRetrieve" if choice == "keyword" else "SemanticRetrieve"
            current_strategy = existing_plan.get("params", {}).get("strategy")
            return {
                **spec,
                "retrieve": {**spec.get("retrieve", {}), "module": retrieve_module},
                "plan": {
                    "module": "NextStepPlan",
                    "params": {"strategy": current_strategy or "RouteBySupport", "system_prompt": existing_plan.get("params", {}).get("system_prompt")},
                },
            }
        return spec

    if step_key == "output_format":
        choice = str(choice_label)
        if choice not in (_FREE_TEXT_OUTPUT_CHOICES | _INTERACTIVE_OUTPUT_CHOICES):
            return spec
        action_module = "ToolCallAction" if choice in _TOOL_CALL_OUTPUT_CHOICES else "GenerativeAction"
        existing_action_params = spec.get("action", {}).get("params", {})
        return {
            **spec,
            "action": {
                "module": action_module,
                "params": {
                    **existing_action_params,
                    "output_format": choice,
                    "tools": [] if action_module != "ToolCallAction" else existing_action_params.get("tools", []),
                    "tool_choice": None if action_module != "ToolCallAction" else existing_action_params.get("tool_choice"),
                },
            },
        }

    if step_key == "failure_policy":
        choice = str(choice_label)
        existing_retrieve_module = spec.get("retrieve", {}).get("module", "PassThroughRetrieve")
        if existing_retrieve_module == "SemanticRetrieve":
            reflect_module = "EvidenceCheckReflect"
        else:
            reflect_module = "ResponseCheckReflect"
        existing_plan = spec.get("plan", {})
        current_strategy = existing_plan.get("params", {}).get("strategy")

        if choice == "retry":
            return {
                **spec,
                "reflect": {"module": reflect_module, "params": {"on_failure": "retry_plan"}},
                "plan": {
                    "module": "NextStepPlan",
                    "params": {"strategy": current_strategy or "RouteBySupport", "system_prompt": existing_plan.get("params", {}).get("system_prompt")},
                },
            }
        elif choice == "handoff":
            return {
                **spec,
                "reflect": {"module": reflect_module, "params": {"on_failure": "end"}},
            }
        return spec

    if step_key == "perceive" and isinstance(choice_label, dict):
        existing_params = spec.get("perceive", {}).get("params", {})
        new_params = dict(existing_params)
        if "input_label" in choice_label:
            new_params["input_label"] = _clean_short_text(str(choice_label["input_label"]), "") or None
        if "welcome_message" in choice_label:
            new_params["welcome_message"] = _clean_prompt(str(choice_label["welcome_message"])) or None
        if "intent_pairs" in choice_label:
            new_params["options"] = list(_option_items_from_pairs(str(choice_label["intent_pairs"])))
        if "importance" in choice_label:
            new_params["importance"] = max(0.0, min(5.0, float(choice_label["importance"] or 1.0)))
        if "image_instruction" in choice_label:
            new_params["image_instruction"] = _clean_prompt(str(choice_label["image_instruction"])) or None
        return {**spec, "perceive": {**spec.get("perceive", {}), "params": new_params}}

    if step_key == "retrieve" and isinstance(choice_label, dict):
        existing_params = spec.get("retrieve", {}).get("params", {})
        new_params = dict(existing_params)
        if "retrieve_description" in choice_label:
            new_params["description"] = _clean_prompt(str(choice_label["retrieve_description"])) or None
        if {"keyword_pairs", "keywords", "content"} & set(choice_label):
            new_params["items"] = list(_retrieve_items_from_payload(choice_label))
        if "fallback" in choice_label:
            new_params["fallback"] = _clean_short_text(str(choice_label["fallback"]), "沒有命中任何條目。")
        if "top_k" in choice_label:
            new_params["top_k"] = max(1, min(20, int(choice_label["top_k"] or 3)))
        if "semantic_support_files" in choice_label:
            new_params["support_files"] = list(_string_items_from_lines(str(choice_label["semantic_support_files"])))
        if "semantic_search_goal" in choice_label:
            new_params["search_goal"] = _clean_prompt(str(choice_label["semantic_search_goal"])) or None
        return {**spec, "retrieve": {**spec.get("retrieve", {}), "params": new_params}}

    if step_key == "action" and isinstance(choice_label, dict):
        existing_action = spec.get("action", {})
        existing_params = existing_action.get("params", {})
        new_params = dict(existing_params)
        action_module = existing_action.get("module", "DirectAnswerAction")

        action_prompt = _action_prompt_from_payload(choice_label, existing_params.get("system_prompt"))
        payload_tools = tuple(_tools_from_action_payload(choice_label)) if _payload_has_interactive_contract(choice_label) else ()

        if payload_tools:
            action_module = "ToolCallAction"
            new_params["tools"] = list(payload_tools)
            new_params["tool_choice"] = "none"
        elif action_module == "ToolCallAction" and not payload_tools:
            new_params["tools"] = existing_params.get("tools") or []

        if action_module == "GenerativeAction" and existing_params.get("output_format") in _STRUCTURED_OUTPUT_CHOICES:
            action_prompt = _fixed_format_action_prompt_from_payload(choice_label, action_prompt)
        new_params["system_prompt"] = action_prompt

        if "direct_memory_key" in choice_label:
            new_params["memory_key"] = _clean_allowed_value(str(choice_label["direct_memory_key"]), _ALLOWED_DIRECT_RESULT_KEYS, DEFAULT_RETRIEVED_CONTENT_KEY)
        if "direct_fallback" in choice_label:
            new_params["fallback"] = _clean_short_text(str(choice_label["direct_fallback"]), "沒有命中任何條目。")
        if "direct_prefix" in choice_label:
            new_params["prefix"] = _clean_short_text(str(choice_label["direct_prefix"]), "")

        return {**spec, "action": {"module": action_module, "params": new_params}}

    return spec


# ---------------------------------------------------------------------------
# Spec → BuilderSourceConfig → Python source
# ---------------------------------------------------------------------------

def spec_to_config(spec: dict[str, Any]) -> BuilderSourceConfig:
    """Convert a v2 spec dict to a BuilderSourceConfig for source compilation."""
    memory = spec.get("memory") or {}
    perceive = spec.get("perceive") or {}
    perceive_params = perceive.get("params") or {}
    retrieve = spec.get("retrieve") or {}
    retrieve_params = retrieve.get("params") or {}
    plan = spec.get("plan") or {}
    plan_params = plan.get("params") or {}
    action = spec.get("action") or {}
    action_params = action.get("params") or {}
    reflect = spec.get("reflect") or {}
    reflect_params = reflect.get("params") or {}
    gates = spec.get("gates") or {}

    perceive_module = perceive.get("module") or "PassThroughPerceive"
    retrieve_module = retrieve.get("module") or "PassThroughRetrieve"
    action_module = action.get("module") or "DirectAnswerAction"
    reflect_module = reflect.get("module") or None
    plan_strategy = plan_params.get("strategy") or None

    return BuilderSourceConfig(
        workflow_name=str(spec.get("workflow_name") or _DEFAULT_WORKFLOW_NAME),
        profile_hint=None,
        task_goal=str(spec.get("description") or "") or None,
        input_kind=_perceive_module_to_input_kind(perceive_module),
        starter_questions=(),  # starter_questions live in runner_presentation, not spec
        perceive_module=perceive_module,
        perceive_input_label=perceive_params.get("input_label") or None,
        perceive_welcome_message=perceive_params.get("welcome_message") or None,
        perceive_options=tuple(o for o in (perceive_params.get("options") or []) if isinstance(o, dict)),
        perceive_importance=float(perceive_params.get("importance") or 1.0),
        perceive_image_instruction=perceive_params.get("image_instruction") or None,
        retrieve_module=retrieve_module,
        retrieve_description=retrieve_params.get("description") or None,
        retrieve_items=tuple(i for i in (retrieve_params.get("items") or []) if isinstance(i, dict)),
        retrieve_fallback=str(retrieve_params.get("fallback") or "沒有命中任何條目。"),
        retrieve_top_k=int(retrieve_params.get("top_k") or 3),
        semantic_support_files=tuple(str(f) for f in (retrieve_params.get("support_files") or []) if str(f).strip()),
        semantic_search_goal=retrieve_params.get("search_goal") or None,
        action_module=action_module,
        action_prompt=_action_system_prompt_from_spec(action_module, action_params),
        action_tools=tuple(action_params.get("tools") or []),
        action_tool_choice=action_params.get("tool_choice") if action_module == "ToolCallAction" else None,
        direct_answer_memory_key=str(action_params.get("memory_key") or DEFAULT_RETRIEVED_CONTENT_KEY),
        direct_answer_fallback=str(action_params.get("fallback") or "沒有命中任何條目。"),
        direct_answer_prefix=str(action_params.get("prefix") or ""),
        custom_action_class="BusinessRule",
        custom_action_memory_key=DEFAULT_RETRIEVED_CONTENT_KEY,
        custom_action_fallback="找不到符合的參考資料。",
        custom_action_prefix="自訂處理結果：",
        custom_rule_title="處理規則",
        custom_rule_instruction=None,
        plan_strategy=plan_strategy,
        plan_system_prompt=plan_params.get("system_prompt") or None,
        reflect_module=reflect_module,
        reflect_on_failure=reflect_params.get("on_failure") or None,
        entry_module=str(spec.get("entry_module") or "perceive"),
        events_schema=spec.get("events") if isinstance(spec.get("events"), dict) else None,
        max_node_hops=int(gates.get("max_node_hops") or 50),
        max_revisit=int(gates.get("max_revisit") or 5),
        timeout_sec=float(gates.get("timeout_sec") or 300.0),
    )


def _perceive_module_to_input_kind(module: str) -> str:
    return {"TextPerceive": "Document", "TextImagePerceive": "TextImage"}.get(module, "Message")


def _action_system_prompt_from_spec(module: str, params: dict) -> str | None:
    raw_prompt = params.get("system_prompt") or None
    if module == "ToolCallAction":
        # ToolCallAction prompt already contains the tool policy in the stored spec
        # but _build_source_for_config will inject it again via _action_system_prompt_for_config
        # So we store the user-authored part only and strip the injected policy if present
        if raw_prompt and _INTERACTIVE_TOOL_POLICY in raw_prompt:
            after_policy = raw_prompt.split("使用者設定的回覆規範：\n", 1)
            return after_policy[1].strip() if len(after_policy) > 1 else None
    return raw_prompt


def compile_python_source(spec: dict[str, Any], *, endpoint_bindings: dict | None = None) -> str:
    """Compile a Python source string from a v2 spec dict."""
    config = spec_to_config(spec)
    return _build_source_for_config(config, endpoint_bindings=endpoint_bindings)


# ---------------------------------------------------------------------------
# Spec → Builder form state (no AST parsing)
# ---------------------------------------------------------------------------

def spec_to_form_state(spec: dict[str, Any], runner_presentation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return Builder form state from a v2 spec dict without parsing Python source."""
    perceive = spec.get("perceive") or {}
    perceive_module = perceive.get("module") or "PassThroughPerceive"
    perceive_params = perceive.get("params") or {}

    retrieve = spec.get("retrieve") or {}
    retrieve_module = retrieve.get("module") or "PassThroughRetrieve"
    retrieve_params = retrieve.get("params") or {}

    plan = spec.get("plan") or {}
    plan_params = plan.get("params") or {}

    action = spec.get("action") or {}
    action_module = action.get("module") or "DirectAnswerAction"
    action_params = action.get("params") or {}

    reflect = spec.get("reflect") or {}
    reflect_module = reflect.get("module") or None
    reflect_params = reflect.get("params") or {}

    # Q1 choices
    memory_kind = (spec.get("memory") or {}).get("kind") or "in_context"
    memory_type_choice = memory_kind if memory_kind in _ALLOWED_MEMORY_KINDS else "in_context"

    # Q2 choices
    input_type_choice = {"TextPerceive": "text", "TextImagePerceive": "text_image"}.get(perceive_module, "pass_through")

    # Q3 choices
    retrieve_policy_choice = {"KeywordRetrieve": "keyword", "SemanticRetrieve": "semantic"}.get(retrieve_module, "none")

    # Q4 choices
    output_format = action_params.get("output_format") or ("interactive" if action_module == "ToolCallAction" else "free_text")

    # Q5 choices
    if reflect_module and reflect_params.get("on_failure") == "retry_plan":
        failure_policy_choice = "retry"
    else:
        failure_policy_choice = "handoff"

    choices: dict[str, str] = {
        "memory_type": memory_type_choice,
        "input_type": input_type_choice,
        "retrieve_policy": retrieve_policy_choice,
        "output_format": output_format,
        "failure_policy": failure_policy_choice,
    }
    workflow_name = str(spec.get("workflow_name") or "")
    if workflow_name and workflow_name not in _GENERATED_WORKFLOW_NAMES and workflow_name != "Untitled Agent":
        choices["name"] = workflow_name

    values: dict[str, dict[str, Any]] = {}

    # Starter questions from runner_presentation (not from spec)
    pres = runner_presentation or {}
    starter_questions = pres.get("starter_questions") or []
    if starter_questions:
        values["memory_type"] = {"starter_questions": "\n".join(str(q) for q in starter_questions)}

    # Perceive params
    if perceive_params.get("input_label"):
        values.setdefault("perceive", {})["input_label"] = perceive_params["input_label"]
    if perceive_params.get("welcome_message"):
        values.setdefault("perceive", {})["welcome_message"] = perceive_params["welcome_message"]
    if perceive_params.get("image_instruction"):
        values.setdefault("perceive", {})["image_instruction"] = perceive_params["image_instruction"]
    options = perceive_params.get("options") or []
    if options:
        values.setdefault("perceive", {})["intent_pairs"] = _pairs_text_from_options(tuple(options))

    # Retrieve params
    items = retrieve_params.get("items") or []
    if items:
        values.setdefault("retrieve", {})["keyword_pairs"] = _pairs_text_from_retrieve_items(tuple(items))
    support_files = retrieve_params.get("support_files") or []
    if support_files:
        values.setdefault("retrieve", {})["semantic_support_files"] = _lines_text_from_items(tuple(support_files))
    if retrieve_params.get("search_goal"):
        values.setdefault("retrieve", {})["semantic_search_goal"] = retrieve_params["search_goal"]
    if retrieve_params.get("description"):
        values.setdefault("retrieve", {})["retrieve_description"] = retrieve_params["description"]

    # Action params
    system_prompt = action_params.get("system_prompt") or None
    if system_prompt:
        values.setdefault("action", {})["response_instruction"] = _response_instruction_from_prompt(system_prompt)
    tools = action_params.get("tools") or []
    if tools:
        values.setdefault("action", {})["api_contracts"] = _api_contracts_json_from_tools(tuple(tools))

    description = str(spec.get("description") or "")
    if description:
        values["description"] = {"agent_description": description}

    return {"choices": choices, "values": values}


# ---------------------------------------------------------------------------
# Spec hash
# ---------------------------------------------------------------------------

def hash_spec(spec: dict[str, Any]) -> str:
    """Return a stable SHA-256 hex digest of the spec."""
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def semantic_bundle_required(spec: dict[str, Any], *, builder_upload_id: str | None = None) -> bool:
    retrieve_module = (spec.get("retrieve") or {}).get("module") or ""
    if retrieve_module != "SemanticRetrieve":
        return False
    if builder_upload_id and str(builder_upload_id).strip():
        return True
    support_files = (spec.get("retrieve") or {}).get("params", {}).get("support_files") or []
    return bool(support_files)


def spec_is_v2(agent: dict) -> bool:
    """True when the agent row has a valid v2 contract stored."""
    return bool(agent.get("playground_contract_version") == "2" and isinstance(agent.get("playground_workflow_spec"), dict))
