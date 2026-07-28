from __future__ import annotations

import ast
import keyword
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playground.models import BuilderChoice, BuilderStep, WorkflowSummary
from playground.services.source_parser import parse_supported_source
from playground.services.workflow_reachability import reachable_workflow_roles


_DEFAULT_WORKFLOW_NAME = "default"
_GENERATED_WORKFLOW_NAMES = {_DEFAULT_WORKFLOW_NAME}

_ACTION_SPECIFIC_PROFILE_HINTS = {"Structured Result", "Custom Action", "OpenAI Client"}
_ACTION_SPECIFIC_WORKFLOW_NAMES = {
    "固定格式 Agent",
    "規則處理 Agent",
    "自然回覆 Agent",
}
_ALLOWED_DIRECT_RESULT_KEYS = {
    "latest_retrieved_content",
    "retrieved_snippet",
    "perceived_input",
    "query",
    "latest_final_message",
}
_ALLOWED_ENTRY_MODULES = {"perceive", "plan", "retrieve", "action"}
_OUTPUT_FORMAT_PROMPTS = {
    "free_text": "請依使用者需求自然回覆；語氣、角色、品牌口吻與回覆方式以使用者設定的回覆風格與規範為準。",
    "interactive": "請同時支援純文字回覆與 OpenAI tool calling。一般問題可自然回答；當需要使用者選擇或填寫資料時，請呼叫最符合的工具，不要把 component/api JSON 當成一般文字輸出。",
    "natural": "請用自然語句回覆；先給結論，再補必要依據與下一步。",
    "bullets": "請用條列摘要回覆；依序列出結論、依據、下一步。",
    "table": "請用表格呈現結果；欄位要清楚，內容要可比較。",
    "json": "請輸出 JSON；欄位固定、值簡潔，不要加入 JSON 以外的文字。",
    "custom_schema": "請依指定格式輸出；欄位缺資料時使用空字串或明確標註未知。",
}
_FREE_TEXT_OUTPUT_CHOICES = {"free_text", "natural", "bullets"}
_INTERACTIVE_OUTPUT_CHOICES = {"interactive", "table", "json", "custom_schema"}
_TOOL_CALL_OUTPUT_CHOICES = {"interactive"}
_STRUCTURED_OUTPUT_CHOICES = {"table", "json", "custom_schema"}
_ADVISOR_REQUIRED_FIELDS_TEXT = "目標 = 使用者想完成的結果\n限制 = 時程、預算、規格或其他約束\n現況 = 已知資料、已嘗試方法或目前阻礙"
_ADVISOR_WELCOME_MESSAGE = "請先描述你想完成的事，我會一步步確認需求。"
_DEFAULT_RETRIEVE_DESCRIPTION = "依使用者設定的關鍵字支援資料判斷是否需要查詢。"
_DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION = "依上傳的支援文件查找與問題最相關的內容。"
_DEFAULT_SEMANTIC_SAVED_PATH = "./tmp"
_DEFAULT_SEMANTIC_SOURCE_DIR = "./tmp/source-files"
_DEFAULT_RUNNER_DESCRIPTION = "可填寫這個 Agent 的用途、適用情境或回覆目標。"
_MODULE_IMPORT_ORDER = (
    "PassThroughPerceive",
    "TextPerceive",
    "TextImagePerceive",
    "NextStepPlan",
    "PassThroughRetrieve",
    "KeywordRetrieve",
    "SemanticRetrieve",
    "EvidenceCheckReflect",
    "ResponseCheckReflect",
    "DirectAnswerAction",
    "GenerativeAction",
    "ToolCallAction",
)


@dataclass(frozen=True)
class BuilderSourceConfig:
    workflow_name: str
    profile_hint: str | None = None
    task_goal: str | None = None
    input_kind: str = "Message"
    starter_questions: tuple[str, ...] = ()
    perceive_module: str = "PassThroughPerceive"
    perceive_input_label: str | None = None
    perceive_welcome_message: str | None = None
    perceive_options: tuple[dict[str, object], ...] = ()
    perceive_importance: float = 1.0
    perceive_image_instruction: str | None = None
    retrieve_module: str = "KeywordRetrieve"
    retrieve_description: str | None = None
    retrieve_items: tuple[dict[str, object], ...] = ()
    retrieve_fallback: str = "沒有命中任何條目。"
    retrieve_top_k: int = 3
    semantic_support_files: tuple[str, ...] = ()
    semantic_search_goal: str | None = None
    action_module: str = "DirectAnswerAction"
    action_prompt: str | None = None
    action_tools: tuple[dict[str, object], ...] = ()
    direct_answer_memory_key: str = "latest_retrieved_content"
    direct_answer_fallback: str = "沒有命中任何條目。"
    direct_answer_prefix: str = ""
    custom_action_class: str = "BusinessRule"
    custom_action_memory_key: str = "latest_retrieved_content"
    custom_action_fallback: str = "找不到符合的支援資料。"
    custom_action_prefix: str = "自訂處理結果："
    custom_rule_title: str = "作業規則"
    custom_rule_instruction: str | None = None
    plan_strategy: str | None = None
    plan_system_prompt: str | None = None
    reflect_module: str | None = None
    reflect_on_failure: str | None = None
    entry_module: str = "perceive"
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0


def get_builder_steps() -> list[BuilderStep]:
    return [
        BuilderStep(
            "memory_type",
            "Q1: 這個 Agent 主要要完成哪類任務？",
            "",
            "Memory 類型",
            "",
            (
                BuilderChoice("in_context", "即時問答", "只根據目前這次對話內容產生問答，不參考先前互動。"),
                BuilderChoice("workflow_recall_preview", "承接前文問答", "問答時需要接續先前互動內容或狀態。", available=False, badge="預覽中"),
            ),
            True,
        ),
        BuilderStep(
            "input_type",
            "Q2: 這個 Agent 要如何理解輸入？",
            "",
            "輸入理解",
            "",
            (
                BuilderChoice("pass_through", "直接傳遞文字", "直接使用目前對話中的文字內容，不先做額外整理或重寫。"),
                BuilderChoice("text", "整理文字內容", "先理解並整理文字內容，再交給後續步驟使用。"),
                BuilderChoice("text_image", "整理文字與圖片", "同時理解文字與圖片內容，再交給後續步驟使用。"),
            ),
            True,
        ),
        BuilderStep(
            "retrieve_policy",
            "Q3: 回答前需要查資料嗎？",
            "",
            "資料查詢",
            "",
            (
                BuilderChoice("none", "不用查", "直接根據輸入或既有流程產生結果。"),
                BuilderChoice("keyword", "關鍵字查詢", "用 key/value 對照表命中固定內容。"),
                BuilderChoice("semantic", "語意搜尋", "依意思找最相關的支援資料。"),
            ),
        ),
        BuilderStep(
            "output_format",
            "Q4: 最後回覆要怎麼呈現給使用者？",
            "",
            "回覆呈現",
            "",
            (
                BuilderChoice("free_text", "純文字回覆", "設定 Agent 的角色、語氣、品牌話術、回答順序與不能說的內容。"),
                BuilderChoice("interactive", "可互動元件", "沿用同一組回覆風格與規範，再追加抽取欄位與 API 提交合約。"),
            ),
        ),
        BuilderStep(
            "failure_policy",
            "Q5: 當 Agent 沒把握時，你希望它怎麼做？",
            "",
            "補救策略",
            "",
            (
                BuilderChoice("retry", "再查一次再回答", "Agent 沒把握時，先重新判斷或重查資料，再試著回答一次。"),
                BuilderChoice("handoff", "先停下來，交給人確認", "Agent 沒把握時先停止，不硬答，保留人工確認空間。"),
            ),
        ),
        BuilderStep(
            "readiness",
            "Q6: 最後確認，準備開始使用",
            "",
            "最後確認",
            "",
            (),
            control="finish",
        ),
    ]


def build_default_python_source() -> str:
    return _build_workflow_source(BuilderSourceConfig(workflow_name=_DEFAULT_WORKFLOW_NAME))


def build_python_source_from_builder_choice(step_key: str, choice_label: object, existing_source: str | None) -> str:
    config = _config_from_source(existing_source)
    if step_key == "name":
        updated = _replace_config(config, workflow_name=_clean_workflow_name(str(choice_label)) or config.workflow_name)
        return _build_source_for_config(updated)

    if step_key == "description":
        updated = _replace_config(config, task_goal=_clean_prompt(str(choice_label)) or None)
        return _build_source_for_config(updated)

    if step_key == "memory_type" and isinstance(choice_label, dict):
        return _build_source_for_config(
            _replace_config(
                config,
                starter_questions=(
                    tuple(_string_items_from_lines(str(choice_label.get("starter_questions", ""))))
                    if "starter_questions" in choice_label
                    else config.starter_questions
                ),
            )
        )

    if step_key == "input_type":
        choice = str(choice_label)
        input_overrides = {
            "pass_through": {
                "input_kind": "Message",
                "perceive_module": "PassThroughPerceive",
                "perceive_welcome_message": None,
                "perceive_options": (),
                "perceive_importance": 1.0,
                "perceive_image_instruction": None,
            },
            "text": {"input_kind": "Document", "perceive_module": "TextPerceive", "perceive_importance": 1.0, "perceive_image_instruction": None},
            "text_image": {"input_kind": "TextImage", "perceive_module": "TextImagePerceive", "perceive_importance": 1.5},
        }
        if choice in input_overrides:
            return _build_source_for_config(_replace_config(config, **input_overrides[choice]))

    if step_key == "retrieve_policy":
        choice = str(choice_label)
        retrieve_overrides = {
            "none": {"retrieve_module": "PassThroughRetrieve", "plan_strategy": None},
            "keyword": {"retrieve_module": "KeywordRetrieve", "plan_strategy": _plan_strategy_for_retrieve_policy(config)},
            "semantic": {"retrieve_module": "SemanticRetrieve", "plan_strategy": _plan_strategy_for_retrieve_policy(config)},
        }
        if choice in retrieve_overrides:
            return _build_source_for_config(_replace_config(config, **retrieve_overrides[choice]))

    if step_key == "output_format":
        choice = str(choice_label)
        if choice in _FREE_TEXT_OUTPUT_CHOICES | _INTERACTIVE_OUTPUT_CHOICES:
            action_module = "ToolCallAction" if choice in _TOOL_CALL_OUTPUT_CHOICES else "GenerativeAction"
            structured_result = action_module == "ToolCallAction" or choice in _STRUCTURED_OUTPUT_CHOICES
            profile_hint = "Structured Result" if structured_result else config.profile_hint
            workflow_name = config.workflow_name
            if not structured_result and action_module == "GenerativeAction" and config.profile_hint in _ACTION_SPECIFIC_PROFILE_HINTS and config.workflow_name in _ACTION_SPECIFIC_WORKFLOW_NAMES:
                profile_hint = None
                workflow_name = _DEFAULT_WORKFLOW_NAME
            return _build_source_for_config(
                _replace_config(
                    config,
                    action_module=action_module,
                    action_prompt=_user_authored_action_prompt(config.action_prompt),
                    action_tools=(),
                    profile_hint=profile_hint,
                    workflow_name=workflow_name,
                )
            )

    if step_key == "failure_policy":
        choice = str(choice_label)
        reflect_module = _reflect_module_for_failure_policy(config)
        failure_overrides = {
            "retry": {"reflect_module": reflect_module, "reflect_on_failure": "retry_plan", "plan_strategy": config.plan_strategy or "RouteBySupport"},
            "handoff": {"reflect_module": reflect_module, "reflect_on_failure": "end", "plan_strategy": config.plan_strategy if reflect_module == "EvidenceCheckReflect" and config.plan_strategy else config.plan_strategy},
            "clarify": {"reflect_module": "ResponseCheckReflect", "reflect_on_failure": "retry_plan", "plan_strategy": config.plan_strategy or "RouteBySupport"},
            "re_retrieve": {"reflect_module": "EvidenceCheckReflect", "reflect_on_failure": "retry_plan", "plan_strategy": config.plan_strategy or "RouteBySupport"},
            "safe_answer": {"reflect_module": "EvidenceCheckReflect", "reflect_on_failure": "end"},
            "escalate": {"reflect_module": "ResponseCheckReflect", "reflect_on_failure": "end"},
        }
        if choice in failure_overrides:
            return _build_source_for_config(_replace_config(config, **failure_overrides[choice]))

    if step_key == "perceive":
        if isinstance(choice_label, dict):
            return _build_source_for_config(
                _replace_config(
                    config,
                    perceive_input_label=_clean_short_text(str(choice_label.get("input_label", config.perceive_input_label or "")), "") if "input_label" in choice_label else config.perceive_input_label,
                    perceive_welcome_message=_clean_prompt(str(choice_label.get("welcome_message", ""))),
                    perceive_options=tuple(_option_items_from_pairs(str(choice_label.get("intent_pairs", "")))) if "intent_pairs" in choice_label else config.perceive_options,
                    perceive_importance=_clean_float(choice_label.get("importance"), config.perceive_importance, 0.0, 5.0),
                    perceive_image_instruction=_clean_prompt(str(choice_label.get("image_instruction", config.perceive_image_instruction or ""))) if "image_instruction" in choice_label else config.perceive_image_instruction,
                )
            )

    if step_key == "retrieve":
        if isinstance(choice_label, dict):
            updated = _replace_config(
                config,
                retrieve_description=_clean_prompt(str(choice_label.get("retrieve_description", config.retrieve_description or ""))) if "retrieve_description" in choice_label else config.retrieve_description,
                retrieve_items=_retrieve_items_from_payload(choice_label) if {"keyword_pairs", "keywords", "content"} & set(choice_label) else config.retrieve_items,
                retrieve_fallback=_clean_short_text(str(choice_label.get("fallback", config.retrieve_fallback)), "沒有命中任何條目。") if "fallback" in choice_label else config.retrieve_fallback,
                retrieve_top_k=_clean_int(choice_label.get("top_k"), config.retrieve_top_k, 1, 20) if "top_k" in choice_label else config.retrieve_top_k,
                semantic_support_files=(
                    tuple(_string_items_from_lines(str(choice_label.get("semantic_support_files", ""))))
                    if "semantic_support_files" in choice_label
                    else config.semantic_support_files
                ),
                semantic_search_goal=(
                    _clean_prompt(str(choice_label.get("semantic_search_goal", config.semantic_search_goal or "")))
                    if "semantic_search_goal" in choice_label
                    else config.semantic_search_goal
                ),
            )
            return _build_source_for_config(updated)

    if step_key == "action":
        if isinstance(choice_label, dict):
            action_prompt = _action_prompt_from_payload(choice_label, config.action_prompt)
            payload_tools = _tools_from_action_payload(choice_label) if _payload_has_interactive_contract(choice_label) else ()
            action_module = "ToolCallAction" if payload_tools else config.action_module
            action_tools = payload_tools or (config.action_tools if action_module == "ToolCallAction" else ())
            if action_module == "GenerativeAction" and config.profile_hint == "Structured Result":
                action_prompt = _fixed_format_action_prompt_from_payload(choice_label, action_prompt)
            updated = _replace_config(
                config,
                action_module=action_module,
                action_prompt=action_prompt,
                action_tools=action_tools,
                direct_answer_memory_key=_clean_allowed_value(str(choice_label.get("direct_memory_key", config.direct_answer_memory_key)), _ALLOWED_DIRECT_RESULT_KEYS, config.direct_answer_memory_key) if "direct_memory_key" in choice_label else config.direct_answer_memory_key,
                direct_answer_fallback=_clean_short_text(str(choice_label.get("direct_fallback", config.direct_answer_fallback)), "沒有命中任何條目。") if "direct_fallback" in choice_label else config.direct_answer_fallback,
                direct_answer_prefix=_clean_short_text(str(choice_label.get("direct_prefix", config.direct_answer_prefix)), "") if "direct_prefix" in choice_label else config.direct_answer_prefix,
                custom_action_class=_clean_python_identifier(str(choice_label.get("class_name", config.custom_action_class)), "BusinessRule"),
                custom_action_memory_key=_clean_identifier_text(str(choice_label.get("memory_key", config.custom_action_memory_key)), "latest_retrieved_content"),
                custom_action_fallback=_clean_short_text(str(choice_label.get("fallback", config.custom_action_fallback)), "找不到符合的支援資料。"),
                custom_action_prefix=_clean_short_text(str(choice_label.get("prefix", config.custom_action_prefix)), "自訂處理結果："),
                custom_rule_title=_clean_short_text(str(choice_label.get("rule_title", config.custom_rule_title)), "作業規則"),
                custom_rule_instruction=(
                    _rule_instruction_from_pairs(str(choice_label.get("rule_pairs", "")))
                    if "rule_pairs" in choice_label
                    else _clean_prompt(str(choice_label.get("rule_instruction", config.custom_rule_instruction or "")))
                    if "rule_instruction" in choice_label
                    else config.custom_rule_instruction
                ),
            )
            return _build_source_for_config(updated)

    return existing_source or build_default_python_source()


def _replace_config(config: BuilderSourceConfig, **overrides: object) -> BuilderSourceConfig:
    values = {
        "workflow_name": config.workflow_name,
        "profile_hint": config.profile_hint,
        "task_goal": config.task_goal,
        "input_kind": config.input_kind,
        "starter_questions": config.starter_questions,
        "perceive_module": config.perceive_module,
        "perceive_input_label": config.perceive_input_label,
        "perceive_welcome_message": config.perceive_welcome_message,
        "perceive_options": config.perceive_options,
        "perceive_importance": config.perceive_importance,
        "perceive_image_instruction": config.perceive_image_instruction,
        "retrieve_module": config.retrieve_module,
        "retrieve_description": config.retrieve_description,
        "retrieve_items": config.retrieve_items,
        "retrieve_fallback": config.retrieve_fallback,
        "retrieve_top_k": config.retrieve_top_k,
        "semantic_support_files": config.semantic_support_files,
        "semantic_search_goal": config.semantic_search_goal,
        "action_module": config.action_module,
        "action_prompt": config.action_prompt,
        "action_tools": config.action_tools,
        "direct_answer_memory_key": config.direct_answer_memory_key,
        "direct_answer_fallback": config.direct_answer_fallback,
        "direct_answer_prefix": config.direct_answer_prefix,
        "custom_action_class": config.custom_action_class,
        "custom_action_memory_key": config.custom_action_memory_key,
        "custom_action_fallback": config.custom_action_fallback,
        "custom_action_prefix": config.custom_action_prefix,
        "custom_rule_title": config.custom_rule_title,
        "custom_rule_instruction": config.custom_rule_instruction,
        "plan_strategy": config.plan_strategy,
        "plan_system_prompt": config.plan_system_prompt,
        "reflect_module": config.reflect_module,
        "reflect_on_failure": config.reflect_on_failure,
        "entry_module": config.entry_module,
        "max_node_hops": config.max_node_hops,
        "max_revisit": config.max_revisit,
        "timeout_sec": config.timeout_sec,
    }
    values.update(overrides)
    return BuilderSourceConfig(**values)  # type: ignore[arg-type]


def _plan_strategy_for_retrieve_policy(config: BuilderSourceConfig) -> str | None:
    return config.plan_strategy or "RouteBySupport"


def _config_from_source(existing_source: str | None) -> BuilderSourceConfig:
    source = existing_source or build_default_python_source()
    parsed = parse_supported_source(source)
    workflow_name = parsed.workflow_name if parsed.workflow_name != "Untitled Agent" else _DEFAULT_WORKFLOW_NAME
    action_call_name = _workflow_action_call_name(source)
    is_custom_action = bool(action_call_name and action_call_name not in {"DirectAnswerAction", "GenerativeAction", "ToolCallAction"})
    runner_config = _safe_config_dict(_extract_assignment_literal(source, "RUNNER_CONFIG", {}))
    semantic_sources = _extract_semantic_sources(source)
    raw_action_prompt = _extract_keyword_value(source, {"GenerativeAction", "ToolCallAction"}, "system_prompt")
    action_tools = tuple(_normalize_tool_items(_extract_keyword_literal(source, {"ToolCallAction"}, "tools", [])))
    action_prompt = _user_authored_action_prompt(raw_action_prompt)
    action_module = "CustomAction" if is_custom_action else action_call_name or "DirectAnswerAction"
    perceive_module = _first_call_name(source, {"PassThroughPerceive", "TextPerceive", "TextImagePerceive"}) or "PassThroughPerceive"

    retrieve_module = _first_call_name(source, {"PassThroughRetrieve", "KeywordRetrieve", "SemanticRetrieve"}) or "KeywordRetrieve"
    workflow_description = _normalize_workflow_description(
        _extract_keyword_value(source, {"Workflow"}, "description")
    )

    return BuilderSourceConfig(
        workflow_name=workflow_name,
        profile_hint=parsed.profile_hint,
        task_goal=workflow_description,
        input_kind=_input_kind_from_source(source),
        starter_questions=tuple(_normalize_string_items(runner_config.get("starter_questions"))),
        perceive_module=perceive_module,
        perceive_input_label=_extract_keyword_value(source, {"PassThroughPerceive"}, "input_label"),
        perceive_welcome_message=_extract_keyword_value(source, {"TextPerceive", "TextImagePerceive"}, "welcome_message"),
        perceive_options=tuple(_normalize_option_items(_extract_keyword_literal(source, {"TextPerceive", "TextImagePerceive"}, "options", []))),
        perceive_importance=_extract_float_value(source, {"TextPerceive", "TextImagePerceive"}, "importance", 1.0),
        perceive_image_instruction=_extract_keyword_value(source, {"TextImagePerceive"}, "image_instruction"),
        retrieve_module=retrieve_module,
        retrieve_description=_extract_keyword_value(source, {"NextStepPlan"}, "retrieve_description"),
        retrieve_items=tuple(_extract_keyword_items(source)),
        retrieve_fallback=_extract_keyword_value(source, {"KeywordRetrieve"}, "fallback") or "沒有命中任何條目。",
        retrieve_top_k=_extract_int_value(source, {"SemanticRetrieve"}, "top_k", 3),
        semantic_support_files=tuple(_semantic_support_files_from_sources(semantic_sources)),
        semantic_search_goal=None,
        action_module=action_module,
        action_prompt=action_prompt,
        action_tools=action_tools,
        direct_answer_memory_key=_clean_allowed_value(_extract_keyword_value(source, {"DirectAnswerAction"}, "memory_key") or "latest_retrieved_content", _ALLOWED_DIRECT_RESULT_KEYS, "latest_retrieved_content"),
        direct_answer_fallback=_extract_keyword_value(source, {"DirectAnswerAction"}, "fallback") or "沒有命中任何條目。",
        direct_answer_prefix=_extract_keyword_value(source, {"DirectAnswerAction"}, "prefix") or "",
        custom_action_class=action_call_name if is_custom_action else "BusinessRule",
        custom_action_memory_key=_extract_custom_action_memory_key(source, _extract_assignment_value(source, "CUSTOM_ACTION_MEMORY_KEY", "latest_retrieved_content")),
        custom_action_fallback=_extract_custom_action_fallback(source, _extract_assignment_value(source, "CUSTOM_ACTION_FALLBACK", "找不到符合的支援資料。")),
        custom_action_prefix=_extract_custom_action_prefix(source, _extract_assignment_value(source, "CUSTOM_ACTION_PREFIX", "自訂處理結果：")),
        custom_rule_title=_extract_custom_action_title(source, _extract_assignment_value(source, "BUSINESS_RULE_TITLE", "作業規則")),
        custom_rule_instruction=_extract_custom_action_instruction(source, _extract_assignment_value(source, "BUSINESS_RULE_INSTRUCTION", "")) or None,
        plan_strategy="RouteBySupport" if "NextStepPlan(" in source else None,
        plan_system_prompt=_extract_keyword_value(source, {"NextStepPlan"}, "system_prompt") or None,
        reflect_module=_first_call_name(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}),
        reflect_on_failure=_extract_keyword_value(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}, "on_failure"),
        entry_module=_clean_allowed_value(_extract_keyword_value(source, {"Workflow"}, "entry_module") or "perceive", _ALLOWED_ENTRY_MODULES, "perceive"),
        max_node_hops=_extract_gates_value(source, "max_node_hops", 50),
        max_revisit=_extract_gates_value(source, "max_revisit", 5),
        timeout_sec=float(_extract_gates_value(source, "timeout_sec", 300.0)),
    )


def config_from_source(existing_source: str | None) -> BuilderSourceConfig:
    return _config_from_source(existing_source)


def normalize_python_source(existing_source: str | None) -> str:
    return _build_source_for_config(_config_from_source(existing_source))


def render_python_source(existing_source: str | None, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    return _build_source_for_config(_config_from_source(existing_source), endpoint_bindings=endpoint_bindings)


def get_builder_form_state(python_source: str, *, include_generated_defaults: bool = False) -> dict[str, object]:
    config = _config_from_source(python_source)
    values: dict[str, dict[str, object]] = {}

    if config.workflow_name not in _GENERATED_WORKFLOW_NAMES and config.workflow_name != "Untitled Agent":
        _add_form_value(values, "name", "agent_name", config.workflow_name)

    _add_form_value(values, "memory_type", "starter_questions", _lines_text_from_items(config.starter_questions))

    _add_form_value(values, "perceive", "input_label", _configured_text(config.perceive_input_label, None, include_generated_defaults))
    _add_form_value(values, "perceive", "welcome_message", _configured_text(config.perceive_welcome_message, _ADVISOR_WELCOME_MESSAGE, include_generated_defaults))
    intent_pairs = _pairs_text_from_options(config.perceive_options)
    if include_generated_defaults or intent_pairs != _ADVISOR_REQUIRED_FIELDS_TEXT:
        _add_form_value(values, "perceive", "intent_pairs", intent_pairs)
    _add_form_value(values, "retrieve", "keyword_pairs", _pairs_text_from_retrieve_items(config.retrieve_items))
    _add_form_value(values, "retrieve", "semantic_support_files", _lines_text_from_items(config.semantic_support_files))
    _add_form_value(values, "retrieve", "semantic_search_goal", _configured_text(config.semantic_search_goal, None, include_generated_defaults))
    _add_form_value(values, "action", "response_instruction", _response_instruction_from_prompt(config.action_prompt))
    _add_form_value(values, "action", "api_contracts", _api_contracts_json_from_tools(config.action_tools))

    return {
        "choices": _builder_choices_for_config(config),
        "values": values,
    }


def _builder_choices_for_config(config: BuilderSourceConfig) -> dict[str, str]:
    input_type = {
        "TextPerceive": "text",
        "TextImagePerceive": "text_image",
    }.get(config.perceive_module, "pass_through")

    if not config.plan_strategy and not config.retrieve_items:
        retrieve_policy = "none"
    else:
        retrieve_policy = {
            "SemanticRetrieve": "semantic",
            "PassThroughRetrieve": "none",
        }.get(config.retrieve_module, "keyword")

    output_format = "free_text"
    if config.action_module == "ToolCallAction":
        output_format = "interactive"

    failure_policy = "handoff"
    if config.reflect_on_failure == "retry_plan":
        failure_policy = "retry"

    return {
        "input_type": input_type,
        "retrieve_policy": retrieve_policy,
        "output_format": output_format,
        "failure_policy": failure_policy,
    }


def _reflect_module_for_failure_policy(config: BuilderSourceConfig) -> str:
    uses_retrieval = config.retrieve_module == "SemanticRetrieve" or bool(config.retrieve_items)
    return "EvidenceCheckReflect" if uses_retrieval else "ResponseCheckReflect"


def _add_form_value(values: dict[str, dict[str, object]], step_key: str, field_name: str, value: object) -> None:
    if value in (None, "", (), []):
        return
    values.setdefault(step_key, {})[field_name] = value


def _configured_text(value: str | None, generated_default: str | None, include_generated_defaults: bool) -> str | None:
    if not value:
        return None
    if not include_generated_defaults and generated_default is not None and value == generated_default:
        return None
    return value


def _pairs_text_from_options(options: tuple[dict[str, object], ...]) -> str:
    return "\n".join(
        f"{str(option.get('label', '')).strip()} = {str(option.get('intent', '')).strip()}"
        for option in options
        if str(option.get("label", "")).strip() and str(option.get("intent", "")).strip()
    )


def _lines_text_from_items(items: tuple[str, ...]) -> str:
    return "\n".join(item for item in items if item)


def _pairs_text_from_retrieve_items(items: tuple[dict[str, object], ...]) -> str:
    lines = []
    for item in items:
        keywords = item.get("keywords")
        content = str(item.get("content", "")).strip()
        if not isinstance(keywords, list) or not content:
            continue
        keyword_text = "、".join(str(keyword).strip() for keyword in keywords if str(keyword).strip())
        if keyword_text:
            lines.append(f"{keyword_text} = {content}")
    return "\n".join(lines)


def _pairs_text_from_rule_instruction(instruction: str | None) -> str:
    if not instruction:
        return ""
    pairs = []
    for line in instruction.splitlines():
        parsed = _split_pair_line(line)
        if parsed is None:
            continue
        key, value = parsed
        key = key.strip()
        value = value.strip()
        if key and value:
            pairs.append(f"{key} = {value}")
    return "\n".join(pairs)


def _response_instruction_from_prompt(prompt: str | None) -> str | None:
    return _user_authored_action_prompt(prompt)


def _api_contracts_json_from_tools(tools: tuple[dict[str, object], ...]) -> str | None:
    contracts = _api_contracts_from_tools(tools)
    if not contracts:
        return None
    return json.dumps(contracts, ensure_ascii=False)


def _api_contracts_from_tools(tools: tuple[dict[str, object], ...]) -> list[dict[str, str]]:
    contracts: list[dict[str, str]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        description = str(function.get("description") or "").strip()
        trigger, api_method, api_url = _interactive_contract_description_parts(description)
        parameters = function.get("parameters")
        contracts.append(
            {
                "interaction_trigger": trigger,
                "api_method": api_method,
                "api_url": api_url,
                "component_fields": _component_fields_text_from_parameters(parameters),
            }
        )
    return [contract for contract in contracts if any(contract.values())]


def _interactive_contract_description_parts(description: str) -> tuple[str, str, str]:
    if "API：" not in description:
        return description, "POST", ""
    trigger, api_part = description.rsplit("API：", 1)
    api_bits = api_part.strip().split(None, 1)
    api_method = api_bits[0].upper() if api_bits else "POST"
    api_url = api_bits[1].strip() if len(api_bits) > 1 else ""
    return trigger.strip(), api_method, api_url


def _component_fields_text_from_parameters(parameters: object) -> str:
    if not isinstance(parameters, dict):
        return ""
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return ""
    type_labels = {"string": "文字", "number": "數字", "boolean": "是/否"}
    lines: list[str] = []
    for name, field in properties.items():
        if not isinstance(field, dict):
            continue
        label = _clean_short_text(str(name), "")
        description = _clean_prompt(str(field.get("description") or "")) or label
        json_type = type_labels.get(str(field.get("type") or "string").lower(), "文字")
        if label and description:
            lines.append(f"{label} = {description}（資料類型：{json_type}）")
    return "\n".join(lines)


def _string_items_from_lines(value: str) -> list[str]:
    return [item for item in (line.strip() for line in value.splitlines()) if item]


def _clean_workflow_name(workflow_name: str) -> str:
    return " ".join(workflow_name.split()).strip()[:64]


def _clean_prompt(prompt: str) -> str | None:
    cleaned = "\n".join(line.rstrip() for line in prompt.strip().splitlines()).strip()
    return cleaned[:500] or None


def _clean_short_text(value: str, fallback: str) -> str:
    cleaned = " ".join(value.split()).strip()
    return cleaned[:160] or fallback


def _clean_identifier_text(value: str, fallback: str) -> str:
    cleaned = "_".join(" ".join(value.split()).replace("-", "_").split())
    allowed = "".join(character for character in cleaned if character.isalnum() or character == "_")
    return allowed[:80] or fallback


def _clean_python_identifier(value: str, fallback: str) -> str:
    cleaned = _clean_identifier_text(value, fallback)
    if cleaned[0].isdigit():
        cleaned = f"Action{cleaned}"
    if keyword.iskeyword(cleaned):
        cleaned = f"{cleaned.title()}Action"
    return cleaned[:80]


def _clean_allowed_value(value: str, allowed_values: set[str], fallback: str) -> str:
    cleaned = value.strip()
    return cleaned if cleaned in allowed_values else fallback


def _action_prompt_from_payload(payload: dict[str, Any], current_prompt: str | None) -> str | None:
    if "response_instruction" in payload:
        return _clean_prompt(str(payload.get("response_instruction", "")))
    return _user_authored_action_prompt(current_prompt)


def _payload_has_interactive_contract(payload: dict[str, Any]) -> bool:
    return bool({"interaction_trigger", "api_method", "api_url", "component_fields", "api_contracts"} & set(payload))


def _fixed_format_action_prompt_from_payload(payload: dict[str, Any], current_prompt: str | None) -> str | None:
    if not ({"rule_title", "rule_pairs"} & set(payload)):
        return current_prompt
    title = _clean_short_text(str(payload.get("rule_title", "")), "")
    rules = _rule_instruction_from_pairs(str(payload.get("rule_pairs", "")))
    if not title and not rules:
        return current_prompt
    parts = [current_prompt or _OUTPUT_FORMAT_PROMPTS["custom_schema"]]
    if title:
        parts.append(f"格式名稱：{title}")
    if rules:
        parts.append(f"固定欄位或規則：\n{rules}")
    return "\n".join(parts)


def _retrieve_items_from_payload(payload: dict[str, Any]) -> tuple[dict[str, object], ...]:
    pair_items = _retrieve_pair_items_from_text(str(payload.get("keyword_pairs", "")))
    if pair_items:
        return tuple(pair_items)

    keywords = _split_keywords(str(payload.get("keywords", "")))
    content = _clean_prompt(str(payload.get("content", "")))
    if not keywords or not content:
        return ()
    return ({"keywords": keywords, "content": content},)


def _retrieve_pair_items_from_text(raw_pairs: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for line in raw_pairs.splitlines():
        parsed = _split_pair_line(line)
        if parsed is None:
            continue
        key, value = parsed
        keywords = _split_keywords(key)
        content = _clean_prompt(value)
        if keywords and content:
            items.append({"keywords": keywords, "content": content})
    return items[:20]


def _config_items_from_pairs(raw_pairs: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in raw_pairs.splitlines():
        parsed = _split_pair_line(line)
        if parsed is None:
            continue
        key, value = parsed
        config_key = _clean_short_text(key, "")
        config_value = _clean_short_text(value, "")
        if config_key and config_value:
            items.append({"key": config_key, "value": config_value})
    return items[:20]


def _option_items_from_pairs(raw_pairs: str) -> list[dict[str, object]]:
    options: list[dict[str, object]] = []
    for item in _config_items_from_pairs(raw_pairs):
        options.append({"label": item["key"], "intent": item["value"]})
    return options


def _split_pair_line(line: str) -> tuple[str, str] | None:
    if "=" in line:
        return line.split("=", 1)
    if "：" in line:
        return line.split("：", 1)
    if ":" in line:
        return line.split(":", 1)
    return None


def _rule_instruction_from_pairs(raw_pairs: str) -> str | None:
    rules: list[str] = []
    for line in raw_pairs.splitlines():
        parsed = _split_pair_line(line)
        if parsed is None:
            continue
        key, value = parsed
        rule_key = _clean_short_text(key, "")
        rule_value = _clean_prompt(value)
        if rule_key and rule_value:
            rules.append(f"{rule_key}：{rule_value}")
    return "\n".join(rules[:20]) or None


def _tools_from_action_payload(payload: dict[str, Any]) -> tuple[dict[str, object], ...]:
    tools = []
    for index, contract in enumerate(_interactive_api_contracts(payload), start=1):
        fields = _tool_parameters_from_pairs(str(contract.get("component_fields") or ""))
        if not fields["properties"]:
            continue
        api_method = str(contract.get("api_method") or "POST")
        api_url = str(contract.get("api_url") or "")
        trigger = str(contract.get("interaction_trigger") or "")
        description_parts = [trigger]
        if api_url:
            description_parts.append(f"API：{api_method} {api_url}")
        description = " ".join(part for part in description_parts if part).strip() or "提交 API 所需資料。"
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"submit_api_{index}",
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": fields["properties"],
                        "required": fields["required"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    return tuple(tools)


def _tool_parameters_from_pairs(raw_pairs: str) -> dict[str, object]:
    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []
    for line in raw_pairs.splitlines():
        parsed = _split_pair_line(line)
        if parsed is None:
            continue
        raw_key, raw_value = parsed
        key = _clean_short_text(raw_key, "")
        description, json_type = _field_description_and_json_type(raw_value)
        if not key or key in properties:
            continue
        properties[key] = {"type": json_type, "description": description or key}
        required.append(key)
    return {"properties": properties, "required": required}


def _field_description_and_json_type(raw_value: str) -> tuple[str, str]:
    value = str(raw_value).strip()
    json_type = "string"
    marker = "（資料類型："
    if marker in value and value.endswith("）"):
        value, raw_type = value.rsplit(marker, 1)
        normalized_type = raw_type.removesuffix("）").strip().lower()
        if "number" in normalized_type or "數字" in normalized_type:
            json_type = "number"
        elif "boolean" in normalized_type or "是/否" in normalized_type:
            json_type = "boolean"
    return (_clean_prompt(value) or "", json_type)


def _split_keywords(raw_keywords: str) -> list[str]:
    separators = [",", "，", "\n", "、"]
    normalized = raw_keywords
    for separator in separators:
        normalized = normalized.replace(separator, "|")
    keywords = []
    for keyword in normalized.split("|"):
        cleaned = " ".join(keyword.split()).strip().lower()
        if cleaned and cleaned not in keywords:
            keywords.append(cleaned)
    return keywords[:8]


def _clean_int(raw_value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, value))


def _clean_float(raw_value: object, fallback: float, minimum: float, maximum: float) -> float:
    try:
        value = float(str(raw_value).strip())
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, value))


def _clean_optional_float(raw_value: object, minimum: float, maximum: float) -> float | None:
    if raw_value in (None, ""):
        return None
    return _clean_float(raw_value, minimum, minimum, maximum)


def _extract_keyword_items(python_source: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) == "KeywordRetrieve":
            for keyword in node.keywords:
                if keyword.arg == "items":
                    try:
                        literal = ast.literal_eval(keyword.value)
                    except (ValueError, SyntaxError):
                        return []
                    if isinstance(literal, list):
                        return _normalize_retrieve_items(literal)
    return []


def _normalize_retrieve_items(raw_items: list[object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        keywords = raw_item.get("keywords")
        content = raw_item.get("content")
        if not isinstance(keywords, list) or not isinstance(content, str):
            continue
        cleaned_keywords = [str(keyword) for keyword in keywords if str(keyword).strip()]
        if cleaned_keywords and content.strip():
            items.append({"keywords": cleaned_keywords, "content": content.strip()})
    return items


def _normalize_tool_items(raw_items: object) -> list[dict[str, object]]:
    if not isinstance(raw_items, list):
        return []
    tools: list[dict[str, object]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, dict) and raw_item.get("type") == "function" and isinstance(raw_item.get("function"), dict):
            tools.append(dict(raw_item))
    return tools[:20]


def _extract_keyword_value(python_source: str, call_names: set[str], keyword_name: str) -> str | None:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in call_names:
            for keyword in node.keywords:
                if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    return keyword.value.value
    return None


def _extract_keyword_literal(python_source: str, call_names: set[str], keyword_name: str, fallback: object) -> object:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in call_names:
            for keyword in node.keywords:
                if keyword.arg == keyword_name:
                    try:
                        return ast.literal_eval(keyword.value)
                    except (ValueError, SyntaxError):
                        return fallback
    return fallback


def _extract_assignment_value(python_source: str, assignment_name: str, fallback: str) -> str:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == assignment_name and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    return fallback


def _extract_custom_action_memory_key(python_source: str, fallback: str) -> str:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "lookup":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                return node.args[0].value
    return fallback


def _extract_custom_action_fallback(python_source: str, fallback: str) -> str:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not any(isinstance(target, ast.Name) and target.id == "summary" for target in node.targets):
            continue
        if isinstance(node.value, ast.BoolOp) and isinstance(node.value.op, ast.Or):
            for value in node.value.values[1:]:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    return fallback


def _extract_custom_action_instruction(python_source: str, fallback: str) -> str:
    return _extract_local_string_assignment(python_source, "instruction", fallback)


def _extract_custom_action_prefix(python_source: str, fallback: str) -> str:
    parts = _custom_action_return_parts(python_source)
    if "summary" in parts:
        summary_index = parts.index("summary")
        for part in reversed(parts[:summary_index]):
            if isinstance(part, str):
                return part
    return fallback


def _extract_custom_action_title(python_source: str, fallback: str) -> str:
    parts = _custom_action_return_parts(python_source)
    if "\n\n" in parts:
        separator_index = parts.index("\n\n")
        for part in parts[separator_index + 1 :]:
            if isinstance(part, str) and part != "：":
                return part
    return fallback


def _extract_local_string_assignment(python_source: str, name: str, fallback: str) -> str:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return fallback


def _custom_action_return_parts(python_source: str) -> list[object]:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return []

    fallback_parts: list[object] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            parts = _flatten_string_addition(node.value)
            if "summary" not in parts:
                continue
            if "\n\n" in parts:
                return parts
            fallback_parts = parts
    return fallback_parts


def _flatten_string_addition(node: ast.AST) -> list[object]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_flatten_string_addition(node.left), *_flatten_string_addition(node.right)]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return [node.id]
    return []


def _extract_assignment_literal(python_source: str, assignment_name: str, fallback: object) -> object:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == assignment_name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return fallback
    return fallback


def _safe_config_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _normalize_option_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    options: list[dict[str, object]] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        label = _clean_short_text(str(raw_item.get("label", "")), "")
        intent = _clean_short_text(str(raw_item.get("intent", "")), "")
        if label and intent:
            options.append({"label": label, "intent": intent})
    return options[:20]


def _extract_int_value(python_source: str, call_names: set[str], keyword_name: str, fallback: int) -> int:
    value = _extract_constant_value(python_source, call_names, keyword_name)
    return value if isinstance(value, int) else fallback


def _extract_float_value(python_source: str, call_names: set[str], keyword_name: str, fallback: float) -> float:
    value = _extract_constant_value(python_source, call_names, keyword_name)
    return float(value) if isinstance(value, (int, float)) else fallback


def _extract_gates_value(python_source: str, keyword_name: str, fallback: int | float) -> int | float:
    direct_value = _extract_constant_value(python_source, {"Gates"}, keyword_name)
    if isinstance(direct_value, (int, float)):
        return direct_value

    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return fallback

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "Workflow":
            continue
        for keyword in node.keywords:
            if keyword.arg != "gates" or not isinstance(keyword.value, ast.Call) or _call_name(keyword.value.func) != "Gates":
                continue
            for gates_keyword in keyword.value.keywords:
                if gates_keyword.arg == keyword_name and isinstance(gates_keyword.value, ast.Constant) and isinstance(gates_keyword.value.value, (int, float)):
                    return gates_keyword.value.value
    return fallback


def _extract_optional_float_value(python_source: str, call_names: set[str], keyword_name: str) -> float | None:
    value = _extract_constant_value(python_source, call_names, keyword_name)
    return float(value) if isinstance(value, (int, float)) else None


def _extract_constant_value(python_source: str, call_names: set[str], keyword_name: str) -> object:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) in call_names:
            for keyword in node.keywords:
                if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
    return None


def _first_call_name(python_source: str, call_names: set[str]) -> str | None:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in call_names:
                return "CustomAction" if call_name == "SummaryAction" else call_name
    return None


def _workflow_action_call_name(python_source: str) -> str | None:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) == "Workflow":
            for keyword_arg in node.keywords:
                if keyword_arg.arg == "action" and isinstance(keyword_arg.value, ast.Call):
                    return _call_name(keyword_arg.value.func)
    return None


def _input_kind_from_source(python_source: str) -> str:
    if "TextImagePerceive(" in python_source:
        return "TextImage"
    if "TextPerceive(" in python_source:
        return "Document"
    return "Message"


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _build_source_for_config(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    if config.profile_hint == "Custom Action" or config.action_module == "CustomAction":
        return _build_custom_action_source(config, endpoint_bindings=endpoint_bindings)
    return _build_workflow_source(config, endpoint_bindings=endpoint_bindings)


def _build_workflow_source(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    workflow_name_literal = json.dumps(config.workflow_name, ensure_ascii=False)
    reachable_roles = reachable_workflow_roles(config)
    workflow_arguments = _workflow_argument_lines(
        config,
        reachable_roles,
        action_expression=_action_expression(config, endpoint_bindings=endpoint_bindings),
        endpoint_bindings=endpoint_bindings,
    )
    workflow_metadata_lines = [f"    workflow_name={workflow_name_literal},"]
    if config.task_goal:
        workflow_metadata_lines.append(f"    description={json.dumps(config.task_goal, ensure_ascii=False)},")
    workflow_block = f"""workflow = Workflow(
{chr(10).join(workflow_metadata_lines)}
{workflow_arguments}
)"""
    import_block = _format_module_imports(_module_names_for_source(workflow_block))
    sections = [_core_import_line(endpoint_bindings)]
    if import_block:
        sections.append(import_block)
    runner_config_block = _runner_config_block(config)
    if runner_config_block:
        sections.append(runner_config_block)
    sections.append(workflow_block)
    return "\n\n".join(sections) + "\n"


def _build_custom_action_source(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    workflow_name_literal = json.dumps(config.workflow_name, ensure_ascii=False)
    custom_action_class = _clean_python_identifier(config.custom_action_class, "BusinessRule")
    memory_key_literal = json.dumps(config.custom_action_memory_key, ensure_ascii=False)
    fallback_literal = json.dumps(config.custom_action_fallback, ensure_ascii=False)
    prefix_literal = json.dumps(config.custom_action_prefix, ensure_ascii=False)
    rule_title_literal = json.dumps(config.custom_rule_title, ensure_ascii=False)
    rule_instruction_literal = json.dumps(config.custom_rule_instruction or "", ensure_ascii=False)
    reachable_roles = reachable_workflow_roles(config)
    workflow_arguments = _workflow_argument_lines(
        config,
        reachable_roles,
        action_expression=f"{custom_action_class}()",
        endpoint_bindings=endpoint_bindings,
    )
    workflow_metadata_lines = [f"    workflow_name={workflow_name_literal},"]
    if config.task_goal:
        workflow_metadata_lines.append(f"    description={json.dumps(config.task_goal, ensure_ascii=False)},")
    workflow_block = f"""class {custom_action_class}:
    def __call__(self, memory):
        summary = memory.lookup({memory_key_literal}) or {fallback_literal}
        instruction = {rule_instruction_literal}
        if instruction:
            return {prefix_literal} + summary + "\\n\\n" + {rule_title_literal} + "：" + instruction
        return {prefix_literal} + summary


workflow = Workflow(
{chr(10).join(workflow_metadata_lines)}
{workflow_arguments}
)
"""
    import_block = _format_module_imports(_module_names_for_source(workflow_block))
    sections = [_core_import_line(endpoint_bindings)]
    if import_block:
        sections.append(import_block)
    runner_config_block = _runner_config_block(config)
    if runner_config_block:
        sections.append(runner_config_block)
    sections.append(workflow_block)
    return "\n\n".join(sections) + "\n"


def _core_import_line(endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    return "from agentic_sdk import Workflow"


def _workflow_argument_lines(
    config: BuilderSourceConfig,
    reachable_roles: set[str],
    *,
    action_expression: str,
    endpoint_bindings: dict[str, dict[str, str]] | None = None,
) -> str:
    lines: list[str] = []
    if "perceive" in reachable_roles:
        lines.append(f"    perceive={_perceive_expression(config, endpoint_bindings=endpoint_bindings)},")
    if "plan" in reachable_roles and config.plan_strategy:
        lines.append(_plan_line(config, reachable_roles, endpoint_bindings=endpoint_bindings).rstrip("\n"))
    if "retrieve" in reachable_roles:
        retrieve_body = _retrieve_expression_body(config, endpoint_bindings=endpoint_bindings)
        if retrieve_body:
            lines.append(f"    retrieve={config.retrieve_module}(")
            lines.append(retrieve_body)
            lines.append("    ),")
        else:
            lines.append(f"    retrieve={config.retrieve_module}(),")
    if "reflect" in reachable_roles and config.reflect_module:
        lines.append(_reflect_line(config, endpoint_bindings=endpoint_bindings).rstrip("\n"))
    if "action" in reachable_roles:
        lines.append(f"    action={action_expression},")
    return "\n".join(lines)


def _action_class_for_config(config: BuilderSourceConfig) -> str:
    if config.action_module == "ToolCallAction":
        return "ToolCallAction"
    if config.action_module == "GenerativeAction":
        return "GenerativeAction"
    return "DirectAnswerAction"


def _action_expression(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    action_class = _action_class_for_config(config)
    if action_class == "DirectAnswerAction":
        arguments = [
            f"memory_key={json.dumps(config.direct_answer_memory_key, ensure_ascii=False)}",
            f"fallback={json.dumps(config.direct_answer_fallback, ensure_ascii=False)}",
            f"prefix={json.dumps(config.direct_answer_prefix, ensure_ascii=False)}",
        ]
        return f"DirectAnswerAction({', '.join(arguments)})"
    arguments = _llm_arguments("ACTION", binding_role="action", endpoint_bindings=endpoint_bindings)
    if config.action_prompt:
        arguments.append(f"system_prompt={json.dumps(config.action_prompt, ensure_ascii=False)}")
    if action_class == "ToolCallAction" and config.action_tools:
        arguments.append(f"tools={_format_python_literal(list(config.action_tools), 8)}")
    return f"{action_class}({', '.join(arguments)})"


def _perceive_expression(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    if config.perceive_module == "PassThroughPerceive":
        if config.perceive_input_label:
            return f"PassThroughPerceive(input_label={json.dumps(config.perceive_input_label, ensure_ascii=False)})"
        return "PassThroughPerceive()"
    arguments = _llm_arguments("PERCEIVE", binding_role="perceive", endpoint_bindings=endpoint_bindings)
    if config.perceive_welcome_message:
        arguments.append(f"welcome_message={json.dumps(config.perceive_welcome_message, ensure_ascii=False)}")
    if config.perceive_options:
        arguments.append(f"options={_format_python_literal(list(config.perceive_options), 8)}")
    if config.perceive_importance != 1.0:
        arguments.append(f"importance={config.perceive_importance}")
    if config.perceive_module == "TextImagePerceive" and config.perceive_image_instruction:
        arguments.append(f"image_instruction={json.dumps(config.perceive_image_instruction, ensure_ascii=False)}")
    return f"{config.perceive_module}({', '.join(arguments)})"


def _retrieve_expression_body(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    if config.retrieve_module == "KeywordRetrieve":
        return f"        items={_format_python_literal(list(config.retrieve_items), 14)},"
    if config.retrieve_module == "PassThroughRetrieve":
        return ""
    arguments = [f"        {argument}," for argument in _llm_arguments("RETRIEVE", binding_role="retrieve", endpoint_bindings=endpoint_bindings)]
    arguments.extend(
        [
            f"        sources={_format_python_literal(_semantic_source_paths(config), 16)},",
        ]
    )
    return "\n".join(arguments)


def _plan_line(config: BuilderSourceConfig, reachable_roles: set[str], endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    description = _retrieve_description(config)
    plan_binding_role = "action" if "action" in reachable_roles else "perceive"
    arguments = [
        *_llm_arguments("PLAN", binding_role=plan_binding_role, endpoint_bindings=endpoint_bindings),
        f"retrieve_description={json.dumps(description, ensure_ascii=False)}",
    ]
    return f"    plan=NextStepPlan({', '.join(arguments)}),\n"


def _reflect_line(config: BuilderSourceConfig, endpoint_bindings: dict[str, dict[str, str]] | None = None) -> str:
    reflect_module = config.reflect_module or "ResponseCheckReflect"
    arguments = _llm_arguments("REFLECT", binding_role="reflect", endpoint_bindings=endpoint_bindings) if reflect_module == "ResponseCheckReflect" else []
    arguments.append(f"on_failure={json.dumps(config.reflect_on_failure, ensure_ascii=False)}")
    return (
        f"    reflect={reflect_module}("
        f"{', '.join(arguments)}"
        "),\n"
    )


def _llm_arguments(
    prefix: str,
    *,
    binding_role: str | None = None,
    endpoint_bindings: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    constant_prefix = _endpoint_constant_prefix(binding_role or prefix)
    model_argument = "embedding_model" if binding_role == "retrieve" else "model"
    model_placeholder_name = "EMBEDDING_MODEL" if binding_role == "retrieve" else "MODEL"
    return [
        f'api_key="<{constant_prefix}_API_KEY>"',
        f'base_url="<{constant_prefix}_API_BASE_URL>"',
        f'{model_argument}="<{constant_prefix}_{model_placeholder_name}>"',
    ]


def _retrieve_description(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "SemanticRetrieve":
        if config.semantic_search_goal:
            return f"優先從這批支援文件查找：{config.semantic_search_goal}"[:240]
        if config.retrieve_description:
            return config.retrieve_description[:240]
        return _DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION
    if config.retrieve_description:
        return config.retrieve_description[:240]
    if config.retrieve_items:
        content = str(config.retrieve_items[0].get("content", "")).strip()
        if content:
            return content[:120]
    return _DEFAULT_RETRIEVE_DESCRIPTION


def _semantic_source_paths(config: BuilderSourceConfig) -> list[str]:
    if not config.semantic_support_files:
        return []
    return [f"./{Path(filename).name}" for filename in config.semantic_support_files]


def _extract_semantic_sources(source: str) -> list[str]:
    return _normalize_string_items(_extract_keyword_literal(source, {"SemanticRetrieve"}, "sources", []))


def _semantic_support_files_from_sources(sources: list[str]) -> list[str]:
    prefix = f"{_DEFAULT_SEMANTIC_SOURCE_DIR}/"
    filenames: list[str] = []
    for source in sources:
        normalized = source.replace("\\", "/")
        if normalized == _DEFAULT_SEMANTIC_SOURCE_DIR:
            continue
        filename = normalized[len(prefix):] if normalized.startswith(prefix) else Path(normalized).name
        if filename:
            filenames.append(filename)
    return filenames


def _endpoint_constant_prefix(role: str) -> str:
    return {
        "perceive": "PERCEIVE",
        "retrieve": "RETRIEVE",
        "action": "ACTION",
        "reflect": "REFLECT",
    }.get(role, role.upper() or "MODEL")


def _format_module_imports(module_names: list[str]) -> str:
    ordered_names = [name for name in _MODULE_IMPORT_ORDER if name in set(module_names)]
    if not ordered_names:
        return ""
    return "from agentic_sdk.modules import (\n    " + ",\n    ".join(ordered_names) + ",\n)"


def _module_names_for_source(python_source: str) -> list[str]:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return []
    used_names = {
        _call_name(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node.func) in set(_MODULE_IMPORT_ORDER)
    }
    return [name for name in _MODULE_IMPORT_ORDER if name in used_names]


def _user_authored_action_prompt(prompt: str | None) -> str | None:
    cleaned = _clean_prompt(str(prompt or ""))
    if not cleaned:
        return None
    if cleaned in _OUTPUT_FORMAT_PROMPTS.values():
        return None
    return cleaned


def _runner_config_block(config: BuilderSourceConfig) -> str:
    if not config.starter_questions:
        return ""
    runner_config = {"starter_questions": list(config.starter_questions)}
    return f"RUNNER_CONFIG = {_format_python_literal(runner_config, 0)}"


def _normalize_workflow_description(value: str | None) -> str | None:
    cleaned = _clean_prompt(str(value or ""))
    if not cleaned:
        return None
    return cleaned


def _format_python_literal(value: object, continuation_indent: int) -> str:
    literal = json.dumps(value, ensure_ascii=False, indent=4)
    literal = literal.replace(": false", ": False").replace(": true", ": True").replace(": null", ": None")
    return literal.replace("\n", "\n" + " " * continuation_indent)


def _normalize_string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (str(entry).strip() for entry in value) if item]


def get_workflow_summary(python_source: str) -> WorkflowSummary:
    parsed = parse_supported_source(python_source)
    name = parsed.workflow_name
    if parsed.profile_hint == "Recommendation":
        template = "建議卡"
        output_contract = "輸出：建議卡"
    elif parsed.profile_hint == "Summary":
        template = "摘要審閱"
        output_contract = "輸出：摘要卡"
    elif parsed.profile_hint == "Structured Form":
        template = "表單收件"
        output_contract = "輸出：摘要卡"
    elif parsed.profile_hint == "Structured Result":
        template = "結構化結果"
        output_contract = "輸出：結果卡"
    elif parsed.profile_hint == "OpenAI Client":
        template = "模型回覆"
        output_contract = "輸出：答案卡"
    elif parsed.profile_hint == "Custom Action":
        template = "自訂處理"
        output_contract = "輸出：自訂結果"
    else:
        template = "回覆助理"
        output_contract = "輸出：回覆內容"

    return WorkflowSummary(
        name=name,
        input_contract="輸入：客戶情境",
        output_contract=output_contract,
        template=template,
        readiness="可開始使用" if parsed.supported_subset else "可預覽",
        can_run=True,
        can_roundtrip=parsed.supported_subset,
    )


def _interactive_api_contracts(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    raw_contracts = str(payload.get("api_contracts", "") or "").strip()
    contracts: list[dict[str, str | None]] = []
    if not raw_contracts:
        return []
    try:
        decoded_contracts = json.loads(raw_contracts)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded_contracts, list):
        return []
    for contract in decoded_contracts:
        if not isinstance(contract, dict):
            continue
        fields = _rule_instruction_from_pairs(str(contract.get("component_fields", "")))
        trigger = _clean_prompt(str(contract.get("interaction_trigger", "")))
        api_method = _clean_short_text(str(contract.get("api_method", "POST")), "POST").upper()
        api_url = _clean_prompt(str(contract.get("api_url", "")))
        if trigger or api_url or fields:
            contracts.append({
                "interaction_trigger": trigger,
                "api_method": api_method,
                "api_url": api_url,
                "component_fields": fields,
            })
    return contracts