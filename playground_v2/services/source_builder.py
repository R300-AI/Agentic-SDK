from __future__ import annotations

import ast
import keyword
import json
from dataclasses import dataclass
from typing import Any

from playground_v2.models import BuilderChoice, BuilderStep, WorkflowSummary
from playground_v2.services.source_parser import parse_supported_source
from playground_v2.services.workflow_reachability import reachable_workflow_roles


_GENERATED_WORKFLOW_NAMES = {
    "Customer Helper": "客戶回覆 Agent",
    "Advisor Helper": "問答引導 Agent",
    "Retrieve Answer Helper": "查資料回答 Agent",
    "Recommendation Helper": "建議型 Agent",
    "Review Summary Helper": "審閱摘要 Agent",
    "Document Review Helper": "審閱摘要 Agent",
    "Structured Intake Helper": "結構化收件 Agent",
    "Structured Result Helper": "固定格式 Agent",
    "OpenAI Client Helper": "自然回覆 Agent",
    "Custom Action Helper": "規則處理 Agent",
}

_ACTION_SPECIFIC_PROFILE_HINTS = {"Structured Result", "Custom Action", "OpenAI Client"}
_ACTION_SPECIFIC_WORKFLOW_NAMES = {"Structured Result Helper", "Custom Action Helper", "OpenAI Client Helper"}
_ALLOWED_DIRECT_RESULT_KEYS = {
    "latest_retrieved_content",
    "retrieved_snippet",
    "perceived_input",
    "query",
    "latest_final_message",
}
_ALLOWED_ENTRY_MODULES = {"perceive", "plan", "retrieve", "action"}
_FORMAL_AUDIENCE_PROMPTS = {
    "customer": "對象是對外客戶；語氣禮貌、清楚，避免內部術語。",
    "executive": "對象是主管或決策者；先給結論、風險與需要決策的事項。",
    "internal": "對象是內部協作夥伴；清楚交代狀態、責任與下一步。",
}
_FORMAL_STRUCTURE_PROMPTS = {
    "conclusion_evidence_next_steps": "結構依序包含：結論、重點依據、下一步。",
    "email_reply": "結構依序包含：稱呼、主旨回覆、補充說明、收尾。",
    "brief_status": "結構依序包含：目前狀態、需要注意的風險、後續動作。",
}
_ADVISOR_QUESTION_MODE_PROMPTS = {
    "one_at_a_time": "每次只問一個最關鍵問題。",
    "two_at_most": "每次最多問兩個彼此相關的問題。",
    "offer_choices": "先提供少量選項協助使用者選擇，再追問缺口。",
}
_ADVISOR_REPLY_STYLE_PROMPTS = {
    "guided": "語氣溫和、引導式，讓使用者容易補充資訊。",
    "diagnostic": "語氣偏診斷式，先指出缺口再提出下一個問題。",
    "concise": "語氣精簡，直接確認下一個必要資訊。",
}
_ADVISOR_RESPONSE_SHAPE_PROMPTS = {
    "known_then_question": "先用一小段整理已知資訊，再提出下一個問題。",
    "question_only": "只提出下一個問題，不提前做結論。",
    "options_then_question": "先列出可選方向，再問使用者要往哪一個方向走。",
}
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
_ADVISOR_HANDOFF_RULE = "當目標、限制與現況足夠明確，或需要支援資料佐證時，才進入查資料或產生整理回覆。"
_ADVISOR_WELCOME_MESSAGE = "請先描述你想完成的事，我會一步步確認需求。"
_DEFAULT_RETRIEVE_DESCRIPTION = "依使用者設定的關鍵字支援資料判斷是否需要查詢。"


@dataclass(frozen=True)
class BuilderSourceConfig:
    workflow_name: str
    profile_hint: str | None = None
    task_goal: str | None = None
    task_success_criteria: str | None = None
    input_kind: str = "Message"
    input_description: str | None = None
    input_fields: tuple[dict[str, str], ...] = ()
    perceive_module: str = "PassThroughPerceive"
    perceive_input_label: str | None = None
    perceive_welcome_message: str | None = None
    perceive_options: tuple[dict[str, object], ...] = ()
    perceive_importance: float = 1.0
    retrieve_module: str = "KeywordRetrieve"
    retrieve_name: str = "支援資料"
    retrieve_description: str | None = None
    retrieve_items: tuple[dict[str, object], ...] = ()
    retrieve_fallback: str = "沒有命中任何條目。"
    retrieve_top_k: int = 3
    retrieve_similarity_weight: float = 0.5
    retrieve_recency_weight: float = 0.3
    retrieve_importance_weight: float = 0.2
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
    plan_direct_rule: str | None = None
    plan_system_prompt: str | None = None
    reflect_module: str | None = None
    reflect_on_failure: str | None = None
    reflect_criteria: str | None = None
    entry_module: str = "perceive"
    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0


def get_builder_steps() -> list[BuilderStep]:
    return [
        BuilderStep(
            "task_type",
            "Q1: 這個 Agent 主要要完成哪類任務？",
            "",
            "任務類型",
            "",
            (
                BuilderChoice("direct_answer", "直接回答", "不先加入自然生成步驟，適合固定答案或規則型回覆。"),
                BuilderChoice("retrieve_answer", "查資料後回答", "先判斷是否需要支援資料，再整理成自然回覆。"),
                BuilderChoice("summarize", "整理摘要", "先理解長文字或文件，再收斂成摘要或判讀結果。"),
                BuilderChoice("structured_output", "產生固定格式", "把輸入整理成表格、JSON 或指定欄位結果。"),
            ),
            True,
        ),
        BuilderStep(
            "input_type",
            "Q2: 使用者會提供什麼資料？",
            "",
            "輸入內容",
            "",
            (
                BuilderChoice("text", "純文字", "直接接收使用者訊息或長文字內容。"),
                BuilderChoice("structured", "表單欄位", "使用固定欄位收集需求。"),
                BuilderChoice("file_image", "圖片或文件", "附件內容會影響判斷。"),
                BuilderChoice("mixed", "混合輸入", "同時接受文字、欄位與附件線索。"),
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
                BuilderChoice("hybrid_later", "混合查詢", "保留關鍵字與語意線索的組合查詢設定。"),
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
            "Q5: 答案不夠有把握時怎麼辦？",
            "",
            "補救策略",
            "",
            (
                BuilderChoice("clarify", "先追問", "檢查不通過時回到規劃步驟補齊缺口。"),
                BuilderChoice("re_retrieve", "重新查資料", "資料或答案不足時重新規劃與查詢。"),
                BuilderChoice("safe_answer", "保守回答", "只輸出已知內容，不強行重試。"),
                BuilderChoice("escalate", "轉人工", "停止自動重試，保留人工確認空間。"),
            ),
        ),
        BuilderStep(
            "readiness",
            "現在可以試跑了嗎？",
            "",
            "試跑",
            "",
            (),
            control="finish",
        ),
    ]


def build_default_python_source() -> str:
    return _build_workflow_source(BuilderSourceConfig(workflow_name="Customer Helper"))


def build_python_source_from_builder_choice(step_key: str, choice_label: object, existing_source: str | None) -> str:
    config = _config_from_source(existing_source)
    if step_key == "name":
        updated = _replace_config(config, workflow_name=_clean_workflow_name(str(choice_label)) or config.workflow_name)
        return _build_source_for_config(updated)

    if step_key == "task_type":
        choice = str(choice_label)
        task_overrides = {
            "direct_answer": {
                "workflow_name": _workflow_name_for_profile(existing_source, "Customer Helper"),
                "profile_hint": None,
                "perceive_module": "PassThroughPerceive",
                "retrieve_module": "KeywordRetrieve",
                "action_module": "DirectAnswerAction",
                "action_prompt": None,
                "plan_strategy": None,
                "reflect_module": None,
                "reflect_on_failure": None,
            },
            "retrieve_answer": {
                "workflow_name": _workflow_name_for_profile(existing_source, "Retrieve Answer Helper"),
                "profile_hint": "Retrieve Answer",
                "perceive_module": "PassThroughPerceive",
                "retrieve_module": "KeywordRetrieve",
                "action_module": "GenerativeAction",
                "action_prompt": _OUTPUT_FORMAT_PROMPTS["natural"],
                "plan_strategy": "RouteBySupport",
                "reflect_module": None,
                "reflect_on_failure": None,
            },
            "summarize": {
                "workflow_name": _workflow_name_for_profile(existing_source, "Review Summary Helper"),
                "profile_hint": "Summary",
                "perceive_module": "TextPerceive",
                "retrieve_module": "SemanticRetrieve",
                "action_module": "GenerativeAction",
                "action_prompt": _OUTPUT_FORMAT_PROMPTS["bullets"],
                "plan_strategy": None,
                "reflect_module": None,
                "reflect_on_failure": None,
            },
            "structured_output": {
                "workflow_name": _workflow_name_for_profile(existing_source, "Structured Result Helper"),
                "profile_hint": "Structured Result",
                "perceive_module": "TextPerceive",
                "retrieve_module": "KeywordRetrieve",
                "action_module": "GenerativeAction",
                "action_prompt": _OUTPUT_FORMAT_PROMPTS["json"],
                "plan_strategy": None,
                "reflect_module": None,
                "reflect_on_failure": None,
            },
        }
        if choice in task_overrides:
            return _build_source_for_config(_replace_config(config, **task_overrides[choice]))

    if step_key == "input_type":
        choice = str(choice_label)
        input_overrides = {
            "text": {"input_kind": "Message", "perceive_module": "PassThroughPerceive"},
            "structured": {"input_kind": "Form", "perceive_module": "TextPerceive"},
            "file_image": {"input_kind": "TextImage", "perceive_module": "TextImagePerceive"},
            "mixed": {"input_kind": "TextImage", "perceive_module": "TextImagePerceive", "perceive_importance": 1.5},
        }
        if choice in input_overrides:
            return _build_source_for_config(_replace_config(config, **input_overrides[choice]))

    if step_key == "retrieve_policy":
        choice = str(choice_label)
        retrieve_overrides = {
            "none": {"retrieve_module": "PassThroughRetrieve", "plan_strategy": None},
            "keyword": {"retrieve_module": "KeywordRetrieve", "plan_strategy": _plan_strategy_for_retrieve_policy(config)},
            "semantic": {"retrieve_module": "SemanticRetrieve", "plan_strategy": _plan_strategy_for_retrieve_policy(config)},
            "hybrid_later": {"retrieve_module": "HybridRetrieve", "plan_strategy": _plan_strategy_for_retrieve_policy(config)},
        }
        if choice in retrieve_overrides:
            return _build_source_for_config(_replace_config(config, **retrieve_overrides[choice]))

    if step_key == "output_format":
        choice = str(choice_label)
        if choice in _FREE_TEXT_OUTPUT_CHOICES | _INTERACTIVE_OUTPUT_CHOICES:
            action_module = "ToolCallAction" if choice in _TOOL_CALL_OUTPUT_CHOICES else "GenerativeAction"
            structured_result = action_module == "ToolCallAction" or choice in _STRUCTURED_OUTPUT_CHOICES
            profile_hint = "Structured Result" if structured_result else config.profile_hint
            workflow_name = _workflow_name_for_profile(existing_source, "Structured Result Helper") if structured_result else config.workflow_name
            if not structured_result and action_module == "GenerativeAction" and config.profile_hint in _ACTION_SPECIFIC_PROFILE_HINTS and config.workflow_name in _ACTION_SPECIFIC_WORKFLOW_NAMES:
                profile_hint = None
                workflow_name = "Customer Helper"
            return _build_source_for_config(
                _replace_config(
                    config,
                    action_module=action_module,
                    action_prompt=_OUTPUT_FORMAT_PROMPTS[choice],
                    action_tools=(),
                    profile_hint=profile_hint,
                    workflow_name=workflow_name,
                )
            )

    if step_key == "failure_policy":
        choice = str(choice_label)
        failure_overrides = {
            "clarify": {"reflect_module": "ResponseCheckReflect", "reflect_on_failure": "retry_plan", "plan_strategy": config.plan_strategy or "RouteBySupport"},
            "re_retrieve": {"reflect_module": "EvidenceCheckReflect", "reflect_on_failure": "retry_plan", "plan_strategy": config.plan_strategy or "RouteBySupport"},
            "safe_answer": {"reflect_module": "EvidenceCheckReflect", "reflect_on_failure": "end"},
            "escalate": {"reflect_module": "ResponseCheckReflect", "reflect_on_failure": "end"},
        }
        if choice in failure_overrides:
            return _build_source_for_config(_replace_config(config, **failure_overrides[choice]))

    if step_key == "template":
        if isinstance(choice_label, dict):
            return _build_source_for_config(
                _replace_config(
                    config,
                    task_goal=_clean_prompt(str(choice_label.get("task_goal", config.task_goal or ""))) if "task_goal" in choice_label else config.task_goal,
                    task_success_criteria=_clean_prompt(str(choice_label.get("success_criteria", config.task_success_criteria or ""))) if "success_criteria" in choice_label else config.task_success_criteria,
                )
            )
        choice = str(choice_label)
        default_names = {
            "Minimal": "Customer Helper",
            "OpenAI client": "OpenAI Client Helper",
            "Custom Action": "Custom Action Helper",
            "Advisor": "Advisor Helper",
            "Recommendation": "Recommendation Helper",
            "Review": "Review Summary Helper",
        }
        profile_hints = {
            "Minimal": None,
            "OpenAI client": "OpenAI Client",
            "Custom Action": "Custom Action",
            "Advisor": "Advisor",
            "Recommendation": "Recommendation",
            "Review": "Summary",
        }
        template_overrides = {
            "Minimal": {"perceive_module": "PassThroughPerceive", "retrieve_module": "KeywordRetrieve", "action_module": "DirectAnswerAction", "plan_strategy": None, "reflect_module": None, "reflect_on_failure": None},
            "OpenAI client": {
                "task_goal": "將使用者輸入整理成可直接對外發送的正式回覆。",
                "task_success_criteria": "語氣專業、先給結論、保留必要依據與下一步，資訊不足時要明確說明。",
                "perceive_module": "PassThroughPerceive",
                "retrieve_module": "KeywordRetrieve",
                "action_module": "GenerativeAction",
                "action_prompt": _formal_response_prompt({}),
                "plan_strategy": None,
                "reflect_module": None,
                "reflect_on_failure": None,
            },
            "Custom Action": {"perceive_module": "PassThroughPerceive", "retrieve_module": "KeywordRetrieve", "action_module": "CustomAction", "plan_strategy": None, "reflect_module": None, "reflect_on_failure": None},
            "Advisor": {
                "task_goal": "一步步釐清使用者需求，缺少關鍵資訊時先追問，不急著給最終結論。",
                "task_success_criteria": "每次只補齊下一個關鍵缺口；資料足夠時再查支援資料或整理回覆。",
                "perceive_module": "TextPerceive",
                "perceive_input_label": "使用者需求",
                "perceive_welcome_message": _ADVISOR_WELCOME_MESSAGE,
                "perceive_options": tuple(_option_items_from_pairs(_ADVISOR_REQUIRED_FIELDS_TEXT)),
                "retrieve_module": "KeywordRetrieve",
                "action_module": "GenerativeAction",
                "action_prompt": _advisor_action_prompt({}),
                "plan_strategy": "RouteBySupport",
                "plan_system_prompt": _advisor_plan_prompt({}),
            },
            "Recommendation": {"perceive_module": "TextPerceive", "retrieve_module": "HybridRetrieve", "action_module": "GenerativeAction", "plan_strategy": "RouteBySupport"},
            "Review": {"perceive_module": "TextPerceive", "retrieve_module": "SemanticRetrieve", "action_module": "GenerativeAction"},
        }
        template_reset = {
            "task_goal": None,
            "task_success_criteria": None,
            "perceive_input_label": None,
            "perceive_welcome_message": None,
            "perceive_options": (),
            "perceive_importance": 1.0,
            "action_prompt": None,
            "plan_direct_rule": None,
            "plan_system_prompt": None,
        }
        if choice in profile_hints:
            template_values = {**template_reset, **template_overrides[choice]}
            updated = _replace_config(
                config,
                workflow_name=_workflow_name_for_profile(existing_source, default_names[choice]),
                profile_hint=profile_hints[choice],
                **template_values,
            )
            return _build_source_for_config(updated)

    if step_key == "input" and isinstance(choice_label, dict):
        return _build_source_for_config(
            _replace_config(
                config,
                input_description=_clean_prompt(str(choice_label.get("input_description", config.input_description or ""))) if "input_description" in choice_label else config.input_description,
                input_fields=tuple(_config_items_from_pairs(str(choice_label.get("input_fields", "")))) if "input_fields" in choice_label else config.input_fields,
                perceive_welcome_message=_clean_prompt(str(choice_label.get("welcome_message", config.perceive_welcome_message or ""))) if "welcome_message" in choice_label else config.perceive_welcome_message,
                perceive_importance=_clean_float(choice_label.get("importance"), config.perceive_importance, 0.0, 5.0) if "importance" in choice_label else config.perceive_importance,
            )
        )

    if step_key == "input" and str(choice_label) == "Message":
        return _build_source_for_config(_replace_config(config, input_kind="Message", perceive_module="PassThroughPerceive"))
    if step_key == "input" and str(choice_label) == "Document":
        return _build_source_for_config(
            _replace_config(
                config,
                input_kind="Document",
                perceive_module="TextPerceive",
                workflow_name=_workflow_name_for_profile(existing_source, "Document Review Helper"),
                profile_hint="Summary",
            )
        )
    if step_key == "input" and str(choice_label) == "Form":
        return _build_source_for_config(
            _replace_config(
                config,
                input_kind="Form",
                perceive_module="TextPerceive",
                workflow_name=_workflow_name_for_profile(existing_source, "Structured Intake Helper"),
                profile_hint="Structured Form",
            )
        )
    if step_key == "input" and str(choice_label) == "TextImage":
        return _build_source_for_config(
            _replace_config(config, input_kind="TextImage", perceive_module="TextImagePerceive", profile_hint="Text Image")
        )

    if step_key == "perceive":
        if isinstance(choice_label, dict):
            return _build_source_for_config(
                _replace_config(
                    config,
                    perceive_input_label=_clean_short_text(str(choice_label.get("input_label", config.perceive_input_label or "")), "") if "input_label" in choice_label else config.perceive_input_label,
                    perceive_welcome_message=_clean_prompt(str(choice_label.get("welcome_message", ""))),
                    perceive_options=tuple(_option_items_from_pairs(str(choice_label.get("intent_pairs", "")))) if "intent_pairs" in choice_label else config.perceive_options,
                    perceive_importance=_clean_float(choice_label.get("importance"), config.perceive_importance, 0.0, 5.0),
                )
            )
        perceive_module = {
            "Simple": "PassThroughPerceive",
            "Text": "TextPerceive",
            "Structured": "TextPerceive",
            "TextImage": "TextImagePerceive",
        }.get(str(choice_label), config.perceive_module)
        return _build_source_for_config(_replace_config(config, perceive_module=perceive_module))

    if step_key == "retrieve":
        if isinstance(choice_label, dict):
            updated = _replace_config(
                config,
                retrieve_name=_clean_short_text(str(choice_label.get("retrieve_name", config.retrieve_name)), "支援資料") if "retrieve_name" in choice_label else config.retrieve_name,
                retrieve_description=_clean_prompt(str(choice_label.get("retrieve_description", config.retrieve_description or ""))) if "retrieve_description" in choice_label else config.retrieve_description,
                retrieve_items=_retrieve_items_from_payload(choice_label) if {"keyword_pairs", "keywords", "content"} & set(choice_label) else config.retrieve_items,
                retrieve_fallback=_clean_short_text(str(choice_label.get("fallback", config.retrieve_fallback)), "沒有命中任何條目。") if "fallback" in choice_label else config.retrieve_fallback,
                retrieve_top_k=_clean_int(choice_label.get("top_k"), config.retrieve_top_k, 1, 20) if "top_k" in choice_label else config.retrieve_top_k,
                retrieve_similarity_weight=_clean_float(choice_label.get("similarity_weight"), config.retrieve_similarity_weight, 0.0, 1.0) if "similarity_weight" in choice_label else config.retrieve_similarity_weight,
                retrieve_recency_weight=_clean_float(choice_label.get("recency_weight"), config.retrieve_recency_weight, 0.0, 1.0) if "recency_weight" in choice_label else config.retrieve_recency_weight,
                retrieve_importance_weight=_clean_float(choice_label.get("importance_weight"), config.retrieve_importance_weight, 0.0, 1.0) if "importance_weight" in choice_label else config.retrieve_importance_weight,
            )
            return _build_source_for_config(updated)
        retrieve_module = {
            "None yet": "KeywordRetrieve",
            "Keyword": "KeywordRetrieve",
            "Semantic": "SemanticRetrieve",
            "Hybrid": "HybridRetrieve",
        }.get(str(choice_label), config.retrieve_module)
        return _build_source_for_config(_replace_config(config, retrieve_module=retrieve_module))

    if step_key == "plan":
        if isinstance(choice_label, dict):
            return _build_source_for_config(
                _replace_config(
                    config,
                    retrieve_name=_clean_short_text(str(choice_label.get("retrieve_name", config.retrieve_name)), "支援資料") if "retrieve_name" in choice_label else config.retrieve_name,
                    retrieve_description=_clean_prompt(str(choice_label.get("retrieve_description", config.retrieve_description or ""))) if "retrieve_description" in choice_label else config.retrieve_description,
                    plan_direct_rule=_clean_prompt(str(choice_label.get("direct_rule", config.plan_direct_rule or ""))) if "direct_rule" in choice_label else config.plan_direct_rule,
                    plan_system_prompt=_plan_prompt_from_payload(choice_label, config.plan_system_prompt),
                )
            )
        plan_strategy = "RouteBySupport" if str(choice_label) == "RouteBySupport" else None
        plan_system_prompt = config.plan_system_prompt if plan_strategy else None
        return _build_source_for_config(_replace_config(config, plan_strategy=plan_strategy, plan_system_prompt=plan_system_prompt))

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
        action_module = {
            "Reply": "DirectAnswerAction",
            "Generative": "GenerativeAction",
            "Structured": "GenerativeAction",
            "ToolCall": "ToolCallAction",
            "Custom": "CustomAction",
        }.get(str(choice_label), config.action_module)
        structured_choice = str(choice_label) == "Structured"
        profile_hint = _profile_hint_for_action_switch(config.profile_hint, action_module)
        workflow_name = _workflow_name_for_action_switch(config, action_module, existing_source)
        if structured_choice:
            profile_hint = "Structured Result"
            workflow_name = _workflow_name_for_profile(existing_source, "Structured Result Helper")
        action_prompt = config.action_prompt if action_module in {"GenerativeAction", "ToolCallAction"} else None
        if structured_choice and not action_prompt:
            action_prompt = _OUTPUT_FORMAT_PROMPTS["json"]
        action_tools = config.action_tools if action_module == "ToolCallAction" else ()
        return _build_source_for_config(
            _replace_config(
                config,
                action_module=action_module,
                profile_hint=profile_hint,
                workflow_name=workflow_name,
                action_prompt=action_prompt,
                action_tools=action_tools,
            )
        )

    if step_key == "reflect":
        if isinstance(choice_label, dict):
            on_failure = str(choice_label.get("on_failure") or config.reflect_on_failure or "retry_plan")
            if on_failure not in {"retry_plan", "end"}:
                on_failure = config.reflect_on_failure or "retry_plan"
            plan_strategy = config.plan_strategy or ("RouteBySupport" if on_failure == "retry_plan" else None)
            return _build_source_for_config(
                _replace_config(
                    config,
                    reflect_on_failure=on_failure,
                    plan_strategy=plan_strategy,
                    reflect_criteria=_clean_prompt(str(choice_label.get("criteria", config.reflect_criteria or ""))) if "criteria" in choice_label else config.reflect_criteria,
                )
            )
        reflect_map = {
            "Later": (None, None),
            "ResponseCheck": ("ResponseCheckReflect", "retry_plan"),
            "EvidenceCheck": ("EvidenceCheckReflect", "retry_plan"),
            "ResponseRetry": ("ResponseCheckReflect", "retry_plan"),
            "ResponseStop": ("ResponseCheckReflect", "end"),
            "EvidenceRetry": ("EvidenceCheckReflect", "retry_plan"),
            "EvidenceStop": ("EvidenceCheckReflect", "end"),
            "RetryPlan": ("ResponseCheckReflect", "retry_plan"),
            "Stop": ("ResponseCheckReflect", "end"),
        }
        reflect_module, reflect_on_failure = reflect_map.get(str(choice_label), (config.reflect_module, config.reflect_on_failure))
        plan_strategy = config.plan_strategy or ("RouteBySupport" if reflect_on_failure == "retry_plan" else None)
        return _build_source_for_config(_replace_config(config, reflect_module=reflect_module, reflect_on_failure=reflect_on_failure, plan_strategy=plan_strategy))

    if step_key == "readiness" and isinstance(choice_label, dict):
        entry_module = _clean_allowed_value(str(choice_label.get("entry_module") or config.entry_module), _ALLOWED_ENTRY_MODULES, config.entry_module)
        updated = _replace_config(
            config,
            entry_module=entry_module,
            plan_strategy=config.plan_strategy or ("RouteBySupport" if entry_module == "plan" else None),
            max_node_hops=_clean_int(choice_label.get("max_node_hops"), config.max_node_hops, 1, 10000),
            max_revisit=_clean_int(choice_label.get("max_revisit"), config.max_revisit, 1, 1000),
            timeout_sec=_clean_float(choice_label.get("timeout_sec"), config.timeout_sec, 1.0, 3600.0),
        )
        return _build_source_for_config(updated)

    return existing_source or build_default_python_source()


def _replace_config(config: BuilderSourceConfig, **overrides: object) -> BuilderSourceConfig:
    values = {
        "workflow_name": config.workflow_name,
        "profile_hint": config.profile_hint,
        "task_goal": config.task_goal,
        "task_success_criteria": config.task_success_criteria,
        "input_kind": config.input_kind,
        "input_description": config.input_description,
        "input_fields": config.input_fields,
        "perceive_module": config.perceive_module,
        "perceive_input_label": config.perceive_input_label,
        "perceive_welcome_message": config.perceive_welcome_message,
        "perceive_options": config.perceive_options,
        "perceive_importance": config.perceive_importance,
        "retrieve_module": config.retrieve_module,
        "retrieve_name": config.retrieve_name,
        "retrieve_description": config.retrieve_description,
        "retrieve_items": config.retrieve_items,
        "retrieve_fallback": config.retrieve_fallback,
        "retrieve_top_k": config.retrieve_top_k,
        "retrieve_similarity_weight": config.retrieve_similarity_weight,
        "retrieve_recency_weight": config.retrieve_recency_weight,
        "retrieve_importance_weight": config.retrieve_importance_weight,
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
        "plan_direct_rule": config.plan_direct_rule,
        "plan_system_prompt": config.plan_system_prompt,
        "reflect_module": config.reflect_module,
        "reflect_on_failure": config.reflect_on_failure,
        "reflect_criteria": config.reflect_criteria,
        "entry_module": config.entry_module,
        "max_node_hops": config.max_node_hops,
        "max_revisit": config.max_revisit,
        "timeout_sec": config.timeout_sec,
    }
    values.update(overrides)
    return BuilderSourceConfig(**values)  # type: ignore[arg-type]


def _plan_strategy_for_retrieve_policy(config: BuilderSourceConfig) -> str | None:
    return "RouteBySupport" if config.profile_hint == "Retrieve Answer" or config.plan_strategy else None


def _config_from_source(existing_source: str | None) -> BuilderSourceConfig:
    source = existing_source or build_default_python_source()
    parsed = parse_supported_source(source)
    workflow_name = parsed.workflow_name if parsed.workflow_name != "Untitled Agent" else "Customer Helper"
    action_call_name = _workflow_action_call_name(source)
    is_custom_action = bool(action_call_name and action_call_name not in {"DirectAnswerAction", "GenerativeAction", "StructuredAction", "ToolCallAction"})
    task_config = _safe_config_dict(_extract_assignment_literal(source, "TASK_CONFIG", {}))
    input_config = _safe_config_dict(_extract_assignment_literal(source, "INPUT_CONFIG", {}))
    perceive_config = _safe_config_dict(_extract_assignment_literal(source, "PERCEIVE_CONFIG", {}))
    retrieve_config = _safe_config_dict(_extract_assignment_literal(source, "RETRIEVE_CONFIG", {}))
    action_config = _safe_config_dict(_extract_assignment_literal(source, "ACTION_CONFIG", {}))
    plan_config = _safe_config_dict(_extract_assignment_literal(source, "PLAN_CONFIG", {}))
    reflect_config = _safe_config_dict(_extract_assignment_literal(source, "REFLECT_CONFIG", {}))
    action_prompt = _extract_keyword_value(source, {"GenerativeAction", "StructuredAction", "ToolCallAction"}, "system_prompt") or _clean_prompt(str(action_config.get("output_guidance", ""))) or None
    action_tools = tuple(_normalize_tool_items(_extract_keyword_literal(source, {"ToolCallAction"}, "tools", action_config.get("tools", []))))
    if not action_tools and action_prompt:
        action_tools = tuple(_tools_from_interactive_prompt(action_prompt))
    action_module = "CustomAction" if is_custom_action else action_call_name or "DirectAnswerAction"
    if action_module == "StructuredAction":
        action_module = "ToolCallAction" if action_tools and _prompt_looks_interactive(action_prompt) else "GenerativeAction"
    perceive_module = _first_call_name(source, {"PassThroughPerceive", "TextPerceive", "StructuredPerceive", "TextImagePerceive"}) or "PassThroughPerceive"
    if perceive_module == "StructuredPerceive":
        perceive_module = "TextPerceive"

    return BuilderSourceConfig(
        workflow_name=workflow_name,
        profile_hint=parsed.profile_hint,
        task_goal=_clean_prompt(str(task_config.get("goal", ""))),
        task_success_criteria=_clean_prompt(str(task_config.get("success_criteria", ""))),
        input_kind=str(input_config.get("kind") or _input_kind_from_source(source)),
        input_description=_clean_prompt(str(input_config.get("description", ""))),
        input_fields=tuple(_normalize_config_items(input_config.get("fields"))),
        perceive_module=perceive_module,
        perceive_input_label=_extract_keyword_value(source, {"PassThroughPerceive"}, "input_label") or _clean_short_text(str(perceive_config.get("input_label", "")), "") or None,
        perceive_welcome_message=_extract_keyword_value(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "welcome_message"),
        perceive_options=tuple(_normalize_option_items(_extract_keyword_literal(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "options", perceive_config.get("options")))),
        perceive_importance=_extract_float_value(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "importance", _clean_float(perceive_config.get("importance"), 1.0, 0.0, 5.0)),
        retrieve_module=_first_call_name(source, {"PassThroughRetrieve", "KeywordRetrieve", "SemanticRetrieve", "HybridRetrieve"}) or "KeywordRetrieve",
        retrieve_name=_extract_keyword_value(source, {"NextStepPlan"}, "retrieve_name") or _clean_short_text(str(retrieve_config.get("name", "支援資料")), "支援資料"),
        retrieve_description=_extract_keyword_value(source, {"NextStepPlan"}, "retrieve_description") or _clean_prompt(str(retrieve_config.get("description", ""))),
        retrieve_items=tuple(_extract_keyword_items(source)),
        retrieve_fallback=_extract_keyword_value(source, {"KeywordRetrieve", "HybridRetrieve"}, "fallback") or _clean_short_text(str(retrieve_config.get("fallback", "沒有命中任何條目。")), "沒有命中任何條目。"),
        retrieve_top_k=_extract_int_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "top_k", _clean_int(retrieve_config.get("top_k"), 3, 1, 20)),
        retrieve_similarity_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "similarity_weight", _clean_float(retrieve_config.get("similarity_weight"), 0.5, 0.0, 1.0)),
        retrieve_recency_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "recency_weight", _clean_float(retrieve_config.get("recency_weight"), 0.3, 0.0, 1.0)),
        retrieve_importance_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "importance_weight", _clean_float(retrieve_config.get("importance_weight"), 0.2, 0.0, 1.0)),
        action_module=action_module,
        action_prompt=action_prompt,
        action_tools=action_tools,
        direct_answer_memory_key=_clean_allowed_value(_extract_keyword_value(source, {"DirectAnswerAction"}, "memory_key") or str(action_config.get("direct_memory_key", "latest_retrieved_content")), _ALLOWED_DIRECT_RESULT_KEYS, "latest_retrieved_content"),
        direct_answer_fallback=_extract_keyword_value(source, {"DirectAnswerAction"}, "fallback") or _clean_short_text(str(action_config.get("direct_fallback", "沒有命中任何條目。")), "沒有命中任何條目。"),
        direct_answer_prefix=_extract_keyword_value(source, {"DirectAnswerAction"}, "prefix") or _clean_short_text(str(action_config.get("direct_prefix", "")), ""),
        custom_action_class=action_call_name if is_custom_action else "BusinessRule",
        custom_action_memory_key=_extract_custom_action_memory_key(source, _extract_assignment_value(source, "CUSTOM_ACTION_MEMORY_KEY", "latest_retrieved_content")),
        custom_action_fallback=_extract_custom_action_fallback(source, _extract_assignment_value(source, "CUSTOM_ACTION_FALLBACK", "找不到符合的支援資料。")),
        custom_action_prefix=_extract_custom_action_prefix(source, _extract_assignment_value(source, "CUSTOM_ACTION_PREFIX", "自訂處理結果：")),
        custom_rule_title=_extract_custom_action_title(source, _extract_assignment_value(source, "BUSINESS_RULE_TITLE", "作業規則")),
        custom_rule_instruction=_extract_custom_action_instruction(source, _extract_assignment_value(source, "BUSINESS_RULE_INSTRUCTION", "")) or None,
        plan_strategy="RouteBySupport" if "NextStepPlan(" in source else None,
        plan_direct_rule=_clean_prompt(str(plan_config.get("direct_rule", ""))),
        plan_system_prompt=_extract_keyword_value(source, {"NextStepPlan"}, "system_prompt") or _clean_prompt(str(plan_config.get("route_rule", ""))) or None,
        reflect_module=_first_call_name(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}),
        reflect_on_failure=_extract_keyword_value(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}, "on_failure"),
        reflect_criteria=_clean_prompt(str(reflect_config.get("criteria", ""))),
        entry_module=_clean_allowed_value(_extract_keyword_value(source, {"Workflow"}, "entry_module") or "perceive", _ALLOWED_ENTRY_MODULES, "perceive"),
        max_node_hops=_extract_gates_value(source, "max_node_hops", 50),
        max_revisit=_extract_gates_value(source, "max_revisit", 5),
        timeout_sec=float(_extract_gates_value(source, "timeout_sec", 300.0)),
    )


def config_from_source(existing_source: str | None) -> BuilderSourceConfig:
    return _config_from_source(existing_source)


def normalize_python_source(existing_source: str | None) -> str:
    return _build_source_for_config(_config_from_source(existing_source))


def get_builder_form_state(python_source: str, *, include_generated_defaults: bool = False) -> dict[str, object]:
    config = _config_from_source(python_source)
    values: dict[str, dict[str, object]] = {}

    if config.workflow_name not in _GENERATED_WORKFLOW_NAMES and config.workflow_name != "Untitled Agent":
        _add_form_value(values, "name", "agent_name", config.workflow_name)

    _add_form_value(values, "perceive", "input_label", _configured_text(config.perceive_input_label, None, include_generated_defaults))
    _add_form_value(values, "perceive", "welcome_message", _configured_text(config.perceive_welcome_message, _ADVISOR_WELCOME_MESSAGE, include_generated_defaults))
    intent_pairs = _pairs_text_from_options(config.perceive_options)
    if include_generated_defaults or intent_pairs != _ADVISOR_REQUIRED_FIELDS_TEXT:
        _add_form_value(values, "perceive", "intent_pairs", intent_pairs)
    if include_generated_defaults or config.perceive_importance != 1.0:
        _add_form_value(values, "perceive", "importance", config.perceive_importance)

    _add_form_value(values, "plan", "retrieve_name", _configured_text(config.retrieve_name, "支援資料", include_generated_defaults))
    _add_form_value(values, "plan", "retrieve_description", _configured_text(config.retrieve_description, _DEFAULT_RETRIEVE_DESCRIPTION, include_generated_defaults))

    _add_form_value(values, "retrieve", "fallback", _configured_text(config.retrieve_fallback, "沒有命中任何條目。", include_generated_defaults))
    _add_form_value(values, "retrieve", "keyword_pairs", _pairs_text_from_retrieve_items(config.retrieve_items))
    if include_generated_defaults or config.retrieve_top_k != 3:
        _add_form_value(values, "retrieve", "top_k", config.retrieve_top_k)
    if include_generated_defaults or config.retrieve_similarity_weight != 0.5:
        _add_form_value(values, "retrieve", "similarity_weight", config.retrieve_similarity_weight)
    if include_generated_defaults or config.retrieve_recency_weight != 0.3:
        _add_form_value(values, "retrieve", "recency_weight", config.retrieve_recency_weight)
    if include_generated_defaults or config.retrieve_importance_weight != 0.2:
        _add_form_value(values, "retrieve", "importance_weight", config.retrieve_importance_weight)

    _add_form_value(values, "action", "direct_memory_key", _configured_text(config.direct_answer_memory_key, "latest_retrieved_content", include_generated_defaults))
    _add_form_value(values, "action", "direct_fallback", _configured_text(config.direct_answer_fallback, "沒有命中任何條目。", include_generated_defaults))
    _add_form_value(values, "action", "direct_prefix", _configured_text(config.direct_answer_prefix, "", include_generated_defaults))
    _add_form_value(values, "action", "rule_title", _configured_text(config.custom_rule_title, "作業規則", include_generated_defaults))
    _add_form_value(values, "action", "rule_pairs", _pairs_text_from_rule_instruction(config.custom_rule_instruction))
    _add_form_value(values, "action", "fallback", _configured_text(config.custom_action_fallback, "找不到符合的支援資料。", include_generated_defaults))
    _add_form_value(values, "action", "prefix", _configured_text(config.custom_action_prefix, "自訂處理結果：", include_generated_defaults))

    if config.reflect_on_failure:
        _add_form_value(values, "reflect", "on_failure", config.reflect_on_failure)

    if include_generated_defaults or config.entry_module != "perceive":
        _add_form_value(values, "readiness", "entry_module", config.entry_module)
    if include_generated_defaults or config.max_node_hops != 50:
        _add_form_value(values, "readiness", "max_node_hops", config.max_node_hops)
    if include_generated_defaults or config.max_revisit != 5:
        _add_form_value(values, "readiness", "max_revisit", config.max_revisit)
    if include_generated_defaults or config.timeout_sec != 300.0:
        _add_form_value(values, "readiness", "timeout_sec", config.timeout_sec)

    return {
        "choices": _builder_choices_for_config(config),
        "values": values,
    }


def _builder_choices_for_config(config: BuilderSourceConfig) -> dict[str, str]:
    template_choice = "Minimal"
    if config.profile_hint == "OpenAI Client":
        template_choice = "OpenAI client"
    elif config.profile_hint == "Custom Action" or config.action_module == "CustomAction":
        template_choice = "Custom Action"
    elif config.profile_hint == "Advisor":
        template_choice = "Advisor"
    elif config.profile_hint == "Recommendation":
        template_choice = "Recommendation"
    elif config.profile_hint == "Summary":
        template_choice = "Review"

    perceive_choice = {
        "PassThroughPerceive": "Simple",
        "TextPerceive": "Text",
        "TextImagePerceive": "TextImage",
    }.get(config.perceive_module, "Simple")
    if config.perceive_module == "TextPerceive" and config.input_kind == "Form":
        perceive_choice = "Structured"
    retrieve_choice = {
        "SemanticRetrieve": "Semantic",
        "HybridRetrieve": "Hybrid",
        "PassThroughRetrieve": "None yet",
    }.get(config.retrieve_module, "Keyword" if config.retrieve_items else "None yet")
    action_choice = {
        "DirectAnswerAction": "Reply",
        "GenerativeAction": "Generative",
        "ToolCallAction": "ToolCall",
        "CustomAction": "Custom",
    }.get(config.action_module, "Reply")
    reflect_choice = {
        "ResponseCheckReflect": "ResponseCheck",
        "EvidenceCheckReflect": "EvidenceCheck",
    }.get(config.reflect_module or "", "Later")

    task_type = "direct_answer"
    if config.profile_hint == "Summary":
        task_type = "summarize"
    elif config.action_module == "ToolCallAction" or config.profile_hint == "Structured Result":
        task_type = "structured_output"
    elif config.plan_strategy or config.profile_hint == "Retrieve Answer":
        task_type = "retrieve_answer"

    input_type = {
        "Form": "structured",
        "TextImage": "file_image",
    }.get(config.input_kind, "text")

    if not config.plan_strategy and not config.retrieve_items:
        retrieve_policy = "none"
    else:
        retrieve_policy = {
            "SemanticRetrieve": "semantic",
            "HybridRetrieve": "hybrid_later",
            "PassThroughRetrieve": "none",
        }.get(config.retrieve_module, "keyword")

    output_format = "free_text"
    if config.action_module == "ToolCallAction":
        output_format = "interactive"

    failure_policy = "safe_answer"
    if config.reflect_module == "ResponseCheckReflect" and config.reflect_on_failure == "retry_plan":
        failure_policy = "clarify"
    elif config.reflect_module == "EvidenceCheckReflect" and config.reflect_on_failure == "retry_plan":
        failure_policy = "re_retrieve"
    elif config.reflect_module == "ResponseCheckReflect" and config.reflect_on_failure == "end":
        failure_policy = "escalate"

    return {
        "template": template_choice,
        "input": config.input_kind,
        "perceive": perceive_choice,
        "plan": "RouteBySupport" if config.plan_strategy else "Direct",
        "retrieve": retrieve_choice,
        "action": action_choice,
        "reflect": reflect_choice,
        "task_type": task_type,
        "input_type": input_type,
        "retrieve_policy": retrieve_policy,
        "output_format": output_format,
        "failure_policy": failure_policy,
    }


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


def _workflow_name_for_profile(existing_source: str | None, default_name: str) -> str:
    parsed = parse_supported_source(existing_source or "")
    if parsed.workflow_name and parsed.workflow_name not in _GENERATED_WORKFLOW_NAMES and parsed.workflow_name != "Untitled Agent":
        return parsed.workflow_name
    return default_name


def _profile_hint_for_action_switch(current_profile_hint: str | None, action_module: str) -> str | None:
    if action_module == "ToolCallAction":
        return "Structured Result"
    if action_module == "CustomAction":
        return "Custom Action"
    if current_profile_hint in _ACTION_SPECIFIC_PROFILE_HINTS:
        return None
    return current_profile_hint


def _workflow_name_for_action_switch(config: BuilderSourceConfig, action_module: str, existing_source: str | None) -> str:
    if action_module == "ToolCallAction":
        return _workflow_name_for_profile(existing_source, "Structured Result Helper")
    if action_module == "CustomAction":
        return _workflow_name_for_profile(existing_source, "Custom Action Helper")
    if config.profile_hint in _ACTION_SPECIFIC_PROFILE_HINTS and config.workflow_name in _ACTION_SPECIFIC_WORKFLOW_NAMES:
        return "Customer Helper"
    return config.workflow_name


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
    keys = set(payload)
    interactive_keys = {"interaction_trigger", "api_method", "api_url", "component_fields", "api_contracts"}
    if "response_instruction" in keys and not (interactive_keys & keys):
        return _single_response_instruction_prompt(payload, current_prompt)
    if {"response_instruction", *interactive_keys} & keys and _prompt_looks_interactive(current_prompt):
        return _interactive_action_prompt(payload, current_prompt)
    if {"brand_voice", "response_guidance", "style_examples"} & keys:
        return _free_text_action_prompt(payload, current_prompt)
    if {"interaction_trigger", "component_type", "component_fields", "component_actions", "api_method", "api_url"} & keys:
        return _interactive_action_prompt(payload, current_prompt)
    if {"formal_audience", "formal_structure", "formal_constraints"} & keys:
        return _formal_response_prompt(payload)
    if {"reply_style", "response_shape"} & keys:
        return _advisor_action_prompt(payload)
    if "output_guidance" in payload:
        return _clean_prompt(str(payload.get("output_guidance", "")))
    if "system_prompt" in payload:
        return _clean_prompt(str(payload.get("system_prompt", "")))
    return current_prompt


def _payload_has_interactive_contract(payload: dict[str, Any]) -> bool:
    return bool({"interaction_trigger", "api_method", "api_url", "component_fields", "api_contracts"} & set(payload))


def _tools_from_interactive_prompt(prompt: str) -> tuple[dict[str, object], ...]:
    if not _prompt_looks_interactive(prompt):
        return ()
    contracts: list[dict[str, str]] = []
    current = {"interaction_trigger": "", "api_method": "POST", "api_url": "", "component_fields": ""}
    field_lines: list[str] = []
    collecting_fields = False
    for raw_line in str(prompt).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "互動元件觸發條件：" in line:
            if field_lines:
                current["component_fields"] = "\n".join(field_lines)
                contracts.append(dict(current))
                current = {"interaction_trigger": "", "api_method": "POST", "api_url": "", "component_fields": ""}
                field_lines = []
            collecting_fields = False
            current["interaction_trigger"] = line.split("互動元件觸發條件：", 1)[1].strip()
            continue
        if "API 提交設定：" in line:
            collecting_fields = False
            api_text = line.split("API 提交設定：", 1)[1].strip()
            api_parts = api_text.split(None, 1)
            if api_parts:
                current["api_method"] = api_parts[0].upper()
            if len(api_parts) > 1:
                current["api_url"] = api_parts[1].strip()
            continue
        if "需要收集的資訊：" in line:
            collecting_fields = True
            trailing = line.split("需要收集的資訊：", 1)[1].strip()
            if trailing:
                field_lines.append(trailing)
            continue
        if collecting_fields:
            if line.startswith(("互動輸出請", "回覆風格", "元件類型", "操作按鈕")) or "API 提交設定：" in line:
                collecting_fields = False
                continue
            field_lines.append(line)
    if field_lines:
        current["component_fields"] = "\n".join(field_lines)
        contracts.append(dict(current))
    if not contracts:
        return ()
    return _tools_from_action_payload({"api_contracts": json.dumps(contracts, ensure_ascii=False)})


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


def _plan_prompt_from_payload(payload: dict[str, Any], current_prompt: str | None) -> str | None:
    if {"question_mode", "missing_info_fields", "handoff_rule"} & set(payload):
        return _advisor_plan_prompt(payload)
    if "route_rule" in payload:
        return _clean_prompt(str(payload.get("route_rule", current_prompt or "")))
    if "system_prompt" in payload:
        return _clean_prompt(str(payload.get("system_prompt", current_prompt or "")))
    return current_prompt


def _formal_response_prompt(payload: dict[str, Any]) -> str:
    audience = _clean_allowed_value(str(payload.get("formal_audience", "customer")), set(_FORMAL_AUDIENCE_PROMPTS), "customer")
    structure = _clean_allowed_value(str(payload.get("formal_structure", "conclusion_evidence_next_steps")), set(_FORMAL_STRUCTURE_PROMPTS), "conclusion_evidence_next_steps")
    constraints = _clean_prompt(str(payload.get("formal_constraints", "不可捏造資料；資訊不足時要明確說明。")))
    parts = [
        "請將使用者輸入整理成可直接發送的正式回覆。",
        _FORMAL_AUDIENCE_PROMPTS[audience],
        _FORMAL_STRUCTURE_PROMPTS[structure],
        "用台灣繁體中文；語氣專業、具體，不使用空泛寒暄。",
    ]
    if constraints:
        parts.append(f"額外限制：{constraints}")
    return "\n".join(parts)


def _advisor_plan_prompt(payload: dict[str, Any]) -> str:
    question_mode = _clean_allowed_value(str(payload.get("question_mode", "one_at_a_time")), set(_ADVISOR_QUESTION_MODE_PROMPTS), "one_at_a_time")
    missing_info_fields = _clean_prompt(str(payload.get("missing_info_fields", _ADVISOR_REQUIRED_FIELDS_TEXT)))
    handoff_rule = _clean_prompt(str(payload.get("handoff_rule", _ADVISOR_HANDOFF_RULE)))
    parts = [
        "請用一步步詢問的方式規劃下一步。",
        f"詢問節奏：{_ADVISOR_QUESTION_MODE_PROMPTS[question_mode]}",
    ]
    if missing_info_fields:
        parts.append(f"優先補齊資訊：\n{missing_info_fields}")
    if handoff_rule:
        parts.append(f"進入查資料或最終回覆的條件：{handoff_rule}")
    return "\n".join(parts)


def _advisor_action_prompt(payload: dict[str, Any]) -> str:
    reply_style = _clean_allowed_value(str(payload.get("reply_style", "guided")), set(_ADVISOR_REPLY_STYLE_PROMPTS), "guided")
    response_shape = _clean_allowed_value(str(payload.get("response_shape", "known_then_question")), set(_ADVISOR_RESPONSE_SHAPE_PROMPTS), "known_then_question")
    return "\n".join(
        [
            "請用一步步詢問的方式回覆，不要在資訊不足時直接給最終結論。",
            _ADVISOR_REPLY_STYLE_PROMPTS[reply_style],
            _ADVISOR_RESPONSE_SHAPE_PROMPTS[response_shape],
            "問題要具體、可回答，避免一次丟出過多開放式問題。",
        ]
    )


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
        if "number" in normalized_type:
            json_type = "number"
        elif "boolean" in normalized_type:
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
        if isinstance(node, ast.Call) and _call_name(node.func) in {"KeywordRetrieve", "HybridRetrieve"}:
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


def _normalize_config_items(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, str]] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        key = _clean_short_text(str(raw_item.get("key", "")), "")
        item_value = _clean_short_text(str(raw_item.get("value", "")), "")
        if key and item_value:
            items.append({"key": key, "value": item_value})
    return items[:20]


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
    if "StructuredPerceive(" in python_source or "Structured Intake Helper" in python_source:
        return "Form"
    if "TextPerceive(" in python_source:
        return "Document"
    return "Message"


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _build_source_for_config(config: BuilderSourceConfig) -> str:
    if config.profile_hint == "Custom Action" or config.action_module == "CustomAction":
        return _build_custom_action_source(config)
    return _build_workflow_source(config)


def _build_workflow_source(config: BuilderSourceConfig) -> str:
    workflow_name_literal = json.dumps(config.workflow_name, ensure_ascii=False)
    reachable_roles = reachable_workflow_roles(config)
    module_names = []
    if "retrieve" in reachable_roles:
        module_names.append(config.retrieve_module)
    if "perceive" in reachable_roles:
        module_names.append(config.perceive_module)
    if "action" in reachable_roles:
        module_names.append(_action_class_for_config(config))
    if "plan" in reachable_roles and config.plan_strategy:
        module_names.append("NextStepPlan")
    if "reflect" in reachable_roles and config.reflect_module:
        module_names.append(config.reflect_module)
    import_block = _format_module_imports(module_names)
    workflow_arguments = _workflow_argument_lines(config, reachable_roles, action_expression=_action_expression(config))
    return f"""{_core_import_line(config)}
{import_block}

workflow = Workflow(
    workflow_name={workflow_name_literal},
{workflow_arguments}
)
"""


def _build_custom_action_source(config: BuilderSourceConfig) -> str:
    workflow_name_literal = json.dumps(config.workflow_name, ensure_ascii=False)
    custom_action_class = _clean_python_identifier(config.custom_action_class, "BusinessRule")
    memory_key_literal = json.dumps(config.custom_action_memory_key, ensure_ascii=False)
    fallback_literal = json.dumps(config.custom_action_fallback, ensure_ascii=False)
    prefix_literal = json.dumps(config.custom_action_prefix, ensure_ascii=False)
    rule_title_literal = json.dumps(config.custom_rule_title, ensure_ascii=False)
    rule_instruction_literal = json.dumps(config.custom_rule_instruction or "", ensure_ascii=False)
    reachable_roles = reachable_workflow_roles(config)
    module_names = []
    if "retrieve" in reachable_roles:
        module_names.append(config.retrieve_module)
    if "perceive" in reachable_roles:
        module_names.append(config.perceive_module)
    if "plan" in reachable_roles and config.plan_strategy:
        module_names.append("NextStepPlan")
    if "reflect" in reachable_roles and config.reflect_module:
        module_names.append(config.reflect_module)
    import_block = _format_module_imports(module_names)
    workflow_arguments = _workflow_argument_lines(config, reachable_roles, action_expression=f"{custom_action_class}()")
    return f"""{_core_import_line(config)}
{import_block}

class {custom_action_class}:
    def __call__(self, memory):
        summary = memory.lookup({memory_key_literal}) or {fallback_literal}
        instruction = {rule_instruction_literal}
        if instruction:
            return {prefix_literal} + summary + "\\n\\n" + {rule_title_literal} + "：" + instruction
        return {prefix_literal} + summary


workflow = Workflow(
    workflow_name={workflow_name_literal},
{workflow_arguments}
)
"""


def _core_import_line(config: BuilderSourceConfig) -> str:
    if _uses_custom_gates(config):
        return "from agentic_sdk import Gates, Workflow"
    return "from agentic_sdk import Workflow"


def _uses_custom_gates(config: BuilderSourceConfig) -> bool:
    return (config.max_node_hops, config.max_revisit, config.timeout_sec) != (50, 5, 300.0)


def _workflow_argument_lines(config: BuilderSourceConfig, reachable_roles: set[str], *, action_expression: str) -> str:
    lines: list[str] = []
    if _uses_custom_gates(config):
        lines.append(f"    gates=Gates(max_node_hops={config.max_node_hops}, max_revisit={config.max_revisit}, timeout_sec={config.timeout_sec}),")
    if config.entry_module != "perceive":
        lines.append(f"    entry_module={json.dumps(config.entry_module, ensure_ascii=False)},")
    if "perceive" in reachable_roles:
        lines.append(f"    perceive={_perceive_expression(config)},")
    if "plan" in reachable_roles and config.plan_strategy:
        lines.append(_plan_line(config).rstrip("\n"))
    if "retrieve" in reachable_roles:
        retrieve_body = _retrieve_expression_body(config)
        if retrieve_body:
            lines.append(f"    retrieve={config.retrieve_module}(")
            lines.append(retrieve_body)
            lines.append("    ),")
        else:
            lines.append(f"    retrieve={config.retrieve_module}(),")
    if "reflect" in reachable_roles and config.reflect_module:
        lines.append(_reflect_line(config).rstrip("\n"))
    if "action" in reachable_roles:
        lines.append(f"    action={action_expression},")
    return "\n".join(lines)


def _action_class_for_config(config: BuilderSourceConfig) -> str:
    if config.action_module == "ToolCallAction":
        return "ToolCallAction"
    if config.action_module in {"GenerativeAction", "StructuredAction"}:
        return "GenerativeAction"
    return "DirectAnswerAction"


def _action_expression(config: BuilderSourceConfig) -> str:
    action_class = _action_class_for_config(config)
    if action_class == "DirectAnswerAction":
        arguments = [
            f"memory_key={json.dumps(config.direct_answer_memory_key, ensure_ascii=False)}",
            f"fallback={json.dumps(config.direct_answer_fallback, ensure_ascii=False)}",
            f"prefix={json.dumps(config.direct_answer_prefix, ensure_ascii=False)}",
        ]
        return f"DirectAnswerAction({', '.join(arguments)})"
    arguments = _llm_arguments("ACTION")
    if config.action_prompt:
        arguments.append(f"system_prompt={json.dumps(config.action_prompt, ensure_ascii=False)}")
    if action_class == "ToolCallAction" and config.action_tools:
        arguments.append(f"tools={_format_python_literal(list(config.action_tools), 8)}")
    return f"{action_class}({', '.join(arguments)})"


def _perceive_expression(config: BuilderSourceConfig) -> str:
    if config.perceive_module == "PassThroughPerceive":
        if config.perceive_input_label:
            return f"PassThroughPerceive(input_label={json.dumps(config.perceive_input_label, ensure_ascii=False)})"
        return "PassThroughPerceive()"
    arguments = _llm_arguments("PERCEIVE")
    if config.perceive_welcome_message:
        arguments.append(f"welcome_message={json.dumps(config.perceive_welcome_message, ensure_ascii=False)}")
    if config.perceive_options:
        arguments.append(f"options={_format_python_literal(list(config.perceive_options), 8)}")
    if config.perceive_importance != 1.0:
        arguments.append(f"importance={config.perceive_importance}")
    return f"{config.perceive_module}({', '.join(arguments)})"


def _retrieve_expression_body(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "KeywordRetrieve":
        return (
            f"        items={_format_python_literal(list(config.retrieve_items), 14)},\n"
            f"        fallback={json.dumps(config.retrieve_fallback, ensure_ascii=False)},"
        )
    if config.retrieve_module == "PassThroughRetrieve":
        return ""
    keyword_arguments = ""
    if config.retrieve_module == "HybridRetrieve":
        keyword_arguments = (
            f"        items={_format_python_literal(list(config.retrieve_items), 14)},\n"
            f"        fallback={json.dumps(config.retrieve_fallback, ensure_ascii=False)},\n"
        )
    if keyword_arguments:
        return keyword_arguments.rstrip("\n")
    return ""


def _plan_line(config: BuilderSourceConfig) -> str:
    description = _retrieve_description(config)
    arguments = [
        *_llm_arguments("PLAN"),
        f"retrieve_name={json.dumps(config.retrieve_name, ensure_ascii=False)}",
        f"retrieve_description={json.dumps(description, ensure_ascii=False)}",
    ]
    return f"    plan=NextStepPlan({', '.join(arguments)}),\n"


def _reflect_line(config: BuilderSourceConfig) -> str:
    reflect_module = config.reflect_module or "ResponseCheckReflect"
    arguments = _llm_arguments("REFLECT") if reflect_module == "ResponseCheckReflect" else []
    arguments.append(f"on_failure={json.dumps(config.reflect_on_failure, ensure_ascii=False)}")
    return (
        f"    reflect={reflect_module}("
        f"{', '.join(arguments)}"
        "),\n"
    )


def _llm_arguments(prefix: str) -> list[str]:
    return [
        'api_key="<填入 API key>"',
        'base_url="<填入 OpenAI-compatible base_url>"',
        'model="<填入模型名稱>"',
    ]


def _retrieve_description(config: BuilderSourceConfig) -> str:
    if config.retrieve_description:
        return config.retrieve_description[:240]
    if config.retrieve_items:
        content = str(config.retrieve_items[0].get("content", "")).strip()
        if content:
            return content[:120]
    return _DEFAULT_RETRIEVE_DESCRIPTION


def _task_system_prompt(config: BuilderSourceConfig) -> str | None:
    parts = []
    if config.task_goal:
        parts.append(f"任務目標：{config.task_goal}")
    if config.task_success_criteria:
        parts.append(f"成功條件：{config.task_success_criteria}")
    return "\n".join(parts) or None


def _format_module_imports(module_names: list[str]) -> str:
    ordered_names = [
        name
        for name in (
            "DirectAnswerAction",
            "GenerativeAction",
            "ToolCallAction",
            "EvidenceCheckReflect",
            "PassThroughRetrieve",
            "KeywordRetrieve",
            "SemanticRetrieve",
            "HybridRetrieve",
            "NextStepPlan",
            "PassThroughPerceive",
            "TextPerceive",
            "TextImagePerceive",
            "ResponseCheckReflect",
        )
        if name in set(module_names)
    ]
    if not ordered_names:
        return ""
    return "from agentic_sdk.modules import (\n    " + ",\n    ".join(ordered_names) + ",\n)"


def _format_python_literal(value: object, continuation_indent: int) -> str:
    literal = json.dumps(value, ensure_ascii=False, indent=4)
    literal = literal.replace(": false", ": False").replace(": true", ": True").replace(": null", ": None")
    return literal.replace("\n", "\n" + " " * continuation_indent)


def get_workflow_summary(python_source: str) -> WorkflowSummary:
    parsed = parse_supported_source(python_source)
    name = _GENERATED_WORKFLOW_NAMES.get(parsed.workflow_name, parsed.workflow_name)
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
        readiness="可試跑" if parsed.supported_subset else "可預覽",
        can_run=True,
        can_roundtrip=parsed.supported_subset,
    )


def _free_text_action_prompt(payload: dict[str, Any], current_prompt: str | None) -> str:
    brand_voice = _clean_prompt(str(payload.get("brand_voice", "")))
    style_examples = _clean_prompt(str(payload.get("style_examples", "")))
    response_guidance = _clean_prompt(str(payload.get("response_guidance", "")))
    parts = [current_prompt or _OUTPUT_FORMAT_PROMPTS["free_text"]]
    if brand_voice:
        parts.append(f"AI 角色與口吻：{brand_voice}")
    if style_examples:
        parts.append(f"品牌或情境話術：{style_examples}")
    if response_guidance:
        parts.append(f"回覆方式偏好：{response_guidance}")
    return "\n".join(parts)


def _single_response_instruction_prompt(payload: dict[str, Any], current_prompt: str | None) -> str:
    response_instruction = _clean_prompt(str(payload.get("response_instruction", "")))
    parts = [current_prompt or _OUTPUT_FORMAT_PROMPTS["free_text"]]
    if response_instruction:
        parts.append(f"回覆風格與規範：{response_instruction}")
    return "\n".join(parts)


def _prompt_looks_interactive(current_prompt: str | None) -> bool:
    return bool(current_prompt and ("可互動元件" in current_prompt or "OpenAI tool calling" in current_prompt or "component.fields" in current_prompt or "api.url" in current_prompt))


def _interactive_action_prompt(payload: dict[str, Any], current_prompt: str | None) -> str:
    response_instruction = _clean_prompt(str(payload.get("response_instruction", "")))
    component_type = _clean_short_text(str(payload.get("component_type", "confirmation_card")), "confirmation_card")
    actions = _rule_instruction_from_pairs(str(payload.get("component_actions", "")))
    contracts = _interactive_api_contracts(payload)
    parts = [current_prompt or _OUTPUT_FORMAT_PROMPTS["interactive"]]
    if response_instruction:
        parts.append(f"回覆風格與規範：{response_instruction}")
    for index, contract in enumerate(contracts, start=1):
        prefix = "" if len(contracts) == 1 else f"API {index} - "
        if contract["interaction_trigger"]:
            parts.append(f"{prefix}互動元件觸發條件：{contract['interaction_trigger']}")
        if contract["api_method"] or contract["api_url"]:
            parts.append(f"{prefix}API 提交設定：{contract['api_method']} {contract['api_url']}".strip())
        if contract["component_fields"]:
            parts.append(f"{prefix}需要收集的資訊：\n{contract['component_fields']}")
    if component_type and "component_type" in payload:
        parts.append(f"元件類型：{component_type}")
    if actions:
        parts.append(f"操作按鈕：\n{actions}")
    parts.append("互動輸出請使用 OpenAI tools/function calling 呼叫最符合的 submit_api_* 工具；不要把 component.fields、api.method、api.url 或 api.body 當成一般文字 JSON 輸出。需要收集的資訊會對應工具 arguments 的欄位名稱；資料類型決定 arguments 欄位值的型態，包含 string、number、boolean。資訊不足時先用自然語句追問；資訊齊全時呼叫工具。")
    return "\n".join(parts)


def _interactive_api_contracts(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    raw_contracts = str(payload.get("api_contracts", "") or "").strip()
    contracts: list[dict[str, str | None]] = []
    if raw_contracts:
        try:
            decoded_contracts = json.loads(raw_contracts)
        except json.JSONDecodeError:
            decoded_contracts = []
        if isinstance(decoded_contracts, list):
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
    if contracts:
        return contracts
    fields = _rule_instruction_from_pairs(str(payload.get("component_fields", "")))
    trigger = _clean_prompt(str(payload.get("interaction_trigger", "")))
    api_method = _clean_short_text(str(payload.get("api_method", "POST")), "POST").upper()
    api_url = _clean_prompt(str(payload.get("api_url", "")))
    if trigger or api_url or fields:
        return [{
            "interaction_trigger": trigger,
            "api_method": api_method,
            "api_url": api_url,
            "component_fields": fields,
        }]
    return []