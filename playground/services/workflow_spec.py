"""v2 Workflow Spec – single source of truth for Builder state.

Spec is stored as JSON in the database; Python source is compiled from spec
and is treated as a read-only export, never parsed back.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from playground.services.source_builder import (
    BuilderSourceConfig,
    build_source_for_config,
    tools_from_action_payload,
    payload_has_interactive_contract,
    action_prompt_from_payload,
    fixed_format_action_prompt_from_payload,
    option_items_from_pairs,
    string_items_from_lines,
    retrieve_items_from_payload,
    retrieve_description,
    DEFAULT_RETRIEVE_DESCRIPTION,
    DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION,
    pairs_text_from_retrieve_items,
    pairs_text_from_options,
    lines_text_from_items,
    response_instruction_from_prompt,
    api_contracts_json_from_tools,
    clean_prompt,
    clean_short_text,
    clean_allowed_value,
    clean_workflow_name,
    ALLOWED_DIRECT_RESULT_KEYS,
    INTERACTIVE_TOOL_POLICY,
    ALLOWED_ENTRY_MODULES,
    DIRECT_ANSWER_OUTPUT_CHOICES,
    VOICE_OUTPUT_CHOICES,
    FREE_TEXT_OUTPUT_CHOICES,
    INTERACTIVE_OUTPUT_CHOICES,
    TOOL_CALL_OUTPUT_CHOICES,
    STRUCTURED_OUTPUT_CHOICES,
    DEFAULT_WORKFLOW_NAME,
    GENERATED_WORKFLOW_NAMES,
    DEFAULT_RETRIEVED_CONTENT_KEY,
)

_SPEC_VERSION = "2"
_PRESENTATION_VERSION = "1"

_ALLOWED_MEMORY_KINDS = {"in_context"}
_ALLOWED_PERCEIVE_MODULES = {"PassThroughPerceive", "TextPerceive", "TextImagePerceive", "VoiceTextPerceive"}
_ALLOWED_RETRIEVE_MODULES = {"PassThroughRetrieve", "KeywordRetrieve", "SemanticRetrieve"}
_ALLOWED_ACTION_MODULES = {"DirectAnswerAction", "GenerativeAction", "ToolCallAction", "VoiceAnswerAction"}
_ALLOWED_REFLECT_MODULES = {"EvidenceCheckReflect", "ResponseCheckReflect"}
_ALLOWED_REFLECT_ON_FAILURE = {"retry_plan", "end"}
_ALLOWED_PLAN_STRATEGIES = {"RouteBySupport"}


# ---------------------------------------------------------------------------
# Default spec
# ---------------------------------------------------------------------------

def default_spec(*, workflow_name: str = DEFAULT_WORKFLOW_NAME) -> dict[str, Any]:
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
            # No module until Q4 is answered. A default that names a real module
            # is indistinguishable from a choice, and DirectAnswerAction runs
            # without a model, so an unfinished agent looked finished and needed
            # nothing bound — which is how two empty agents reached the gallery.
            "module": None,
            "params": {
                "output_format": None,
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
        "gates": {"max_node_hops": 50, "max_revisit": 5, "timeout_sec": 300.0, "max_reflect_rounds": 5},
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
        spec["entry_module"] = entry if entry in ALLOWED_ENTRY_MODULES else "perceive"
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
        params["input_label"] = clean_short_text(str(p["input_label"] or ""), "") or None
    if "welcome_message" in p:
        params["welcome_message"] = clean_prompt(str(p["welcome_message"] or "")) or None
    if "options" in p and isinstance(p["options"], list):
        params["options"] = [o for o in p["options"] if isinstance(o, dict) and o.get("label") and o.get("intent")][:20]
    if "importance" in p:
        params["importance"] = max(0.0, min(5.0, float(p["importance"] or 1.0)))
    if "image_instruction" in p:
        params["image_instruction"] = clean_prompt(str(p["image_instruction"] or "")) or None


def _bounded_top_k(raw: object, fallback: int) -> int:
    """How many entries a search returns, clamped to what the module accepts."""
    try:
        value = int(str(raw).strip() or fallback)
    except (TypeError, ValueError):
        return fallback
    return max(1, min(20, value))


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
        params["description"] = clean_prompt(str(p["description"] or "")) or None
    if "items" in p and isinstance(p["items"], list):
        params["items"] = [i for i in p["items"] if isinstance(i, dict)][:100]
    if "fallback" in p:
        params["fallback"] = clean_short_text(str(p["fallback"] or ""), "沒有命中任何條目。")
    if "top_k" in p:
        params["top_k"] = _bounded_top_k(p["top_k"], 3)
    if "support_files" in p and isinstance(p["support_files"], list):
        params["support_files"] = [str(f) for f in p["support_files"] if str(f).strip()][:50]
    if "search_goal" in p:
        params["search_goal"] = clean_prompt(str(p["search_goal"] or "")) or None


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
        params["system_prompt"] = clean_prompt(str(p["system_prompt"] or "")) or None


def _apply_action(spec: dict, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    module = str(raw.get("module") or "") or None
    if module is not None and module not in _ALLOWED_ACTION_MODULES:
        module = None
    spec["action"]["module"] = module
    p = raw.get("params") or {}
    if not isinstance(p, dict):
        return
    params = spec["action"]["params"]
    if "output_format" in p:
        # No output format is a state the spec can hold: nobody has answered
        # Q4 yet. Defaulting it to free_text here wrote an answer the person
        # never gave, and every AI Hub load runs through this.
        if p["output_format"] is None:
            params["output_format"] = None
        else:
            fmt = str(p["output_format"])
            params["output_format"] = fmt if fmt in (FREE_TEXT_OUTPUT_CHOICES | INTERACTIVE_OUTPUT_CHOICES | DIRECT_ANSWER_OUTPUT_CHOICES | VOICE_OUTPUT_CHOICES) else "free_text"
    if "system_prompt" in p:
        params["system_prompt"] = clean_prompt(str(p["system_prompt"] or "")) or None
    if "tools" in p and isinstance(p["tools"], list):
        params["tools"] = list(p["tools"])
    if "tool_choice" in p:
        params["tool_choice"] = p["tool_choice"]
    if "memory_key" in p:
        key = str(p["memory_key"] or DEFAULT_RETRIEVED_CONTENT_KEY)
        params["memory_key"] = key if key in ALLOWED_DIRECT_RESULT_KEYS else DEFAULT_RETRIEVED_CONTENT_KEY
    if "fallback" in p:
        params["fallback"] = clean_short_text(str(p["fallback"] or ""), "沒有命中任何條目。")
    if "prefix" in p:
        params["prefix"] = clean_short_text(str(p["prefix"] or ""), "")


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
    if "max_reflect_rounds" in raw:
        gates["max_reflect_rounds"] = max(1, min(100, int(raw["max_reflect_rounds"] or 5)))


# ---------------------------------------------------------------------------
# Apply Builder step to spec
# ---------------------------------------------------------------------------

def apply_builder_step(spec: dict[str, Any], step_key: str, choice_label: object) -> dict[str, Any]:
    """Return a new spec with the given Builder step applied."""
    spec = dict(spec)  # shallow copy; deep sections are replaced as needed

    if step_key == "name":
        name = clean_workflow_name(str(choice_label)) or spec.get("workflow_name") or DEFAULT_WORKFLOW_NAME
        return {**spec, "workflow_name": name}

    if step_key == "description":
        desc = clean_prompt(str(choice_label)) or ""
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
        elif choice == "voice":
            return {**spec, "perceive": {**spec.get("perceive", {}), "module": "VoiceTextPerceive"}}
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
        elif choice == "semantic":
            # A planner earns its model call by deciding whether to search, and
            # searching here costs an embedding call. Keyword lookup is a
            # dictionary read, so deciding whether to do it costs more than
            # doing it — that flow goes straight to retrieve.
            current_strategy = existing_plan.get("params", {}).get("strategy")
            return {
                **spec,
                "retrieve": {**spec.get("retrieve", {}), "module": "SemanticRetrieve"},
                "plan": {
                    "module": "NextStepPlan",
                    "params": {"strategy": current_strategy or "RouteBySupport", "system_prompt": existing_plan.get("params", {}).get("system_prompt")},
                },
            }
        elif choice == "keyword":
            return {**spec, "retrieve": {**spec.get("retrieve", {}), "module": "KeywordRetrieve"}}
        return spec

    if step_key == "output_format":
        choice = str(choice_label)
        if choice not in (FREE_TEXT_OUTPUT_CHOICES | INTERACTIVE_OUTPUT_CHOICES | DIRECT_ANSWER_OUTPUT_CHOICES | VOICE_OUTPUT_CHOICES):
            return spec
        if choice in VOICE_OUTPUT_CHOICES:
            action_module = "VoiceAnswerAction"
        elif choice in TOOL_CALL_OUTPUT_CHOICES:
            action_module = "ToolCallAction"
        elif choice in DIRECT_ANSWER_OUTPUT_CHOICES:
            action_module = "DirectAnswerAction"
        else:
            action_module = "GenerativeAction"
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
        # Check the evidence when there is evidence to check. Keyword and
        # semantic retrieval both report how many entries they matched, and
        # reading that number costs nothing. Only an agent that looks nothing up
        # has to pay a model to judge its own answer.
        if existing_retrieve_module in {"SemanticRetrieve", "KeywordRetrieve"}:
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
            new_params["input_label"] = clean_short_text(str(choice_label["input_label"]), "") or None
        if "welcome_message" in choice_label:
            new_params["welcome_message"] = clean_prompt(str(choice_label["welcome_message"])) or None
        if "intent_pairs" in choice_label:
            new_params["options"] = list(option_items_from_pairs(str(choice_label["intent_pairs"])))
        if "importance" in choice_label:
            new_params["importance"] = max(0.0, min(5.0, float(choice_label["importance"] or 1.0)))
        if "image_instruction" in choice_label:
            new_params["image_instruction"] = clean_prompt(str(choice_label["image_instruction"])) or None
        return {**spec, "perceive": {**spec.get("perceive", {}), "params": new_params}}

    if step_key == "retrieve" and isinstance(choice_label, dict):
        existing_params = spec.get("retrieve", {}).get("params", {})
        new_params = dict(existing_params)
        if "retrieve_description" in choice_label:
            new_params["description"] = clean_prompt(str(choice_label["retrieve_description"])) or None
        if {"keyword_pairs", "keywords", "content"} & set(choice_label):
            new_params["items"] = list(retrieve_items_from_payload(choice_label))
        if "fallback" in choice_label:
            new_params["fallback"] = clean_short_text(str(choice_label["fallback"]), "沒有命中任何條目。")
        if "top_k" in choice_label:
            # A field someone can type into is a field someone can type words
            # into, and a 500 is a worse answer than keeping what was there.
            new_params["top_k"] = _bounded_top_k(choice_label["top_k"], new_params.get("top_k") or 3)
        if "semantic_support_files" in choice_label:
            new_params["support_files"] = list(string_items_from_lines(str(choice_label["semantic_support_files"])))
        if "semantic_search_goal" in choice_label:
            new_params["search_goal"] = clean_prompt(str(choice_label["semantic_search_goal"])) or None
        return {**spec, "retrieve": {**spec.get("retrieve", {}), "params": new_params}}

    if step_key == "action" and isinstance(choice_label, dict):
        existing_action = spec.get("action", {})
        existing_params = existing_action.get("params", {})
        new_params = dict(existing_params)
        action_module = existing_action.get("module") or ""

        action_prompt = action_prompt_from_payload(choice_label, existing_params.get("system_prompt"))
        payload_tools = tuple(tools_from_action_payload(choice_label)) if payload_has_interactive_contract(choice_label) else ()

        if payload_tools:
            action_module = "ToolCallAction"
            new_params["tools"] = list(payload_tools)
            new_params["tool_choice"] = "auto"
        elif action_module == "ToolCallAction" and not payload_tools:
            new_params["tools"] = existing_params.get("tools") or []

        if action_module == "GenerativeAction" and existing_params.get("output_format") in STRUCTURED_OUTPUT_CHOICES:
            action_prompt = fixed_format_action_prompt_from_payload(choice_label, action_prompt)
        new_params["system_prompt"] = action_prompt

        if "direct_memory_key" in choice_label:
            new_params["memory_key"] = clean_allowed_value(str(choice_label["direct_memory_key"]), ALLOWED_DIRECT_RESULT_KEYS, DEFAULT_RETRIEVED_CONTENT_KEY)
        if "direct_fallback" in choice_label:
            new_params["fallback"] = clean_short_text(str(choice_label["direct_fallback"]), "沒有命中任何條目。")
        if "direct_prefix" in choice_label:
            new_params["prefix"] = clean_short_text(str(choice_label["direct_prefix"]), "")

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
    action_module = action.get("module") or ""
    reflect_module = reflect.get("module") or None
    plan_strategy = plan_params.get("strategy") or None

    config = BuilderSourceConfig(
        workflow_name=str(spec.get("workflow_name") or DEFAULT_WORKFLOW_NAME),
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
    if config.retrieve_description:
        return config
    # The compiled source wrote a derived description into the plan module, but
    # only when it differed from the two defaults. Mirror that exactly: a default
    # description must stay None, because NextStepPlan reads its presence as
    # "this agent has a retrieve source" and changes its routing on that.
    derived = retrieve_description(config)
    if derived in {DEFAULT_RETRIEVE_DESCRIPTION, DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION}:
        return config
    return replace(config, retrieve_description=derived)


def _perceive_module_to_input_kind(module: str) -> str:
    return {"TextPerceive": "Document", "TextImagePerceive": "TextImage"}.get(module, "Message")


def _action_system_prompt_from_spec(module: str, params: dict) -> str | None:
    raw_prompt = params.get("system_prompt") or None
    if module == "ToolCallAction":
        # ToolCallAction prompt already contains the tool policy in the stored spec
        # but build_source_for_config will inject it again via _action_system_prompt_for_config
        # So we store the user-authored part only and strip the injected policy if present
        if raw_prompt and INTERACTIVE_TOOL_POLICY in raw_prompt:
            after_policy = raw_prompt.split("使用者設定的回覆規範：\n", 1)
            return after_policy[1].strip() if len(after_policy) > 1 else None
    return raw_prompt


def compile_python_source(spec: dict[str, Any]) -> str:
    """Compile a Python source string from a v2 spec dict."""
    config = spec_to_config(spec)
    return build_source_for_config(config)


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
    action_module = action.get("module") or ""
    action_params = action.get("params") or {}

    reflect = spec.get("reflect") or {}
    reflect_module = reflect.get("module") or None
    reflect_params = reflect.get("params") or {}

    # Q1 choices
    memory_kind = (spec.get("memory") or {}).get("kind") or "in_context"
    memory_type_choice = memory_kind if memory_kind in _ALLOWED_MEMORY_KINDS else "in_context"

    # Q2 choices
    input_type_choice = {"TextPerceive": "text", "TextImagePerceive": "text_image", "VoiceTextPerceive": "voice"}.get(perceive_module, "pass_through")

    # Q3 choices
    retrieve_policy_choice = {"KeywordRetrieve": "keyword", "SemanticRetrieve": "semantic"}.get(retrieve_module, "none")

    # Q4 choices. DirectAnswerAction is what an untouched spec holds and Q4
    # offers no choice for it, so report nothing rather than naming a choice the
    # agent does not have.
    # The module decides, not the stored format. Answering Q4 always installs
    # GenerativeAction or ToolCallAction, so any other module means the question
    # was never answered — whatever output_format the spec happens to carry.
    # Reading the format first let a stored "free_text" beside a DirectAnswer
    # action report an answer nobody gave, and the review page passed it.
    if action_module == "ToolCallAction":
        output_format = str(action_params.get("output_format") or "interactive")
    elif action_module == "GenerativeAction":
        output_format = str(action_params.get("output_format") or "free_text")
    elif action_module == "VoiceAnswerAction":
        output_format = "voice"
    elif action_module == "DirectAnswerAction":
        output_format = "direct"
    else:
        output_format = ""

    # Q5 choices. Both answers install a reflect module, so a spec without one
    # has not answered this question.
    if not reflect_module:
        failure_policy_choice = ""
    elif reflect_params.get("on_failure") == "retry_plan":
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
    if workflow_name and workflow_name not in GENERATED_WORKFLOW_NAMES and workflow_name != "Untitled Agent":
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
        values.setdefault("perceive", {})["intent_pairs"] = pairs_text_from_options(tuple(options))

    # Retrieve params
    items = retrieve_params.get("items") or []
    if items:
        values.setdefault("retrieve", {})["keyword_pairs"] = pairs_text_from_retrieve_items(tuple(items))
    support_files = retrieve_params.get("support_files") or []
    if support_files:
        values.setdefault("retrieve", {})["semantic_support_files"] = lines_text_from_items(tuple(support_files))
    if retrieve_params.get("search_goal"):
        values.setdefault("retrieve", {})["semantic_search_goal"] = retrieve_params["search_goal"]
    # Carried back so the field shows what the agent is actually using, not an
    # empty box that looks like the setting was never made.
    if retrieve_params.get("top_k"):
        values.setdefault("retrieve", {})["top_k"] = str(retrieve_params["top_k"])
    if retrieve_params.get("description"):
        values.setdefault("retrieve", {})["retrieve_description"] = retrieve_params["description"]

    # Action params
    system_prompt = action_params.get("system_prompt") or None
    if system_prompt:
        values.setdefault("action", {})["response_instruction"] = response_instruction_from_prompt(system_prompt)
    tools = action_params.get("tools") or []
    if tools:
        values.setdefault("action", {})["api_contracts"] = api_contracts_json_from_tools(tuple(tools))

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
