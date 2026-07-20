from __future__ import annotations

import ast
import keyword
import json
from dataclasses import dataclass
from typing import Any

from playground_v2.models import BuilderChoice, BuilderStep, WorkflowSummary
from playground_v2.services.source_parser import parse_supported_source


_GENERATED_WORKFLOW_NAMES = {
    "Customer Helper": "客戶回覆 Agent",
    "Advisor Helper": "問答引導 Agent",
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
            "name",
            "這個 Agent 要如何命名？",
            "",
            "Agent 名稱",
            "",
            (),
            True,
            control="text",
        ),
        BuilderStep(
            "template",
            "要先套用哪個起始範本？",
            "",
            "任務類型",
            "",
            (
                BuilderChoice("Minimal", "一般問答", "不預設外部 OpenAI 相容 client，適合先從最小流程開始。"),
                BuilderChoice("OpenAI client", "整理成自然回覆", "沿用外部 OpenAI 相容 client 產生自然語言回覆。"),
                BuilderChoice("Custom Action", "套用作業規則", "用規則 key/value 決定最後處理方式。"),
                BuilderChoice("Advisor", "需求判斷", "先整理需求，再判斷是否需要支援資料。"),
                BuilderChoice("Recommendation", "推薦下一步", "查找支援資料後輸出固定格式建議。"),
                BuilderChoice("Review", "摘要與判讀", "針對長文字或文件做摘要、判讀與整理。"),
            ),
            True,
        ),
        BuilderStep(
            "input",
            "這個 Agent 需要理解什麼資料？",
            "",
            "輸入內容",
            "",
            (
                BuilderChoice("Message", "文字訊息", "直接把使用者輸入當作查詢與回覆依據。"),
                BuilderChoice("Document", "檔案或長文字", "先整理長內容重點，再往後處理。"),
                BuilderChoice("Form", "固定欄位", "用欄位 key/value 定義收件資料。"),
                BuilderChoice("TextImage", "文字與圖片", "同時保留文字描述與圖片附件線索。"),
            ),
            True,
        ),
        BuilderStep(
            "perceive",
            "要如何讀取使用者需求？",
            "",
            "讀取方式",
            "",
            (
                BuilderChoice("Simple", "直接讀取文字訊息", "不另外整理意圖，只保留原始輸入。"),
                BuilderChoice("Text", "先整理需求重點", "用意圖 key/value 協助判斷使用者真正需求。"),
                BuilderChoice("Structured", "依欄位理解需求", "適合表單欄位，需要明確欄位與意圖對照。"),
                BuilderChoice("TextImage", "同時參考文字與圖片", "適合圖片附件會影響判斷的情境。"),
            ),
        ),
        BuilderStep(
            "plan",
            "是否需要決策路徑？",
            "",
            "決策方式",
            "",
            (
                BuilderChoice("Direct", "不需要，直接產生回覆", "不加入判斷步驟，直接產生回覆。"),
                BuilderChoice("RouteBySupport", "需要，先判斷是否查詢支援資料", "用判斷規則與資料用途決定下一步。"),
            ),
        ),
        BuilderStep(
            "retrieve",
            "可以使用哪些支援資料？",
            "",
            "參考資料",
            "",
            (
                BuilderChoice("None yet", "暫不加入支援資料", "只配置沒有命中時的內容。"),
                BuilderChoice("Keyword", "用關鍵字對應內容", "用 key/value 對照表命中固定內容。"),
                BuilderChoice("Semantic", "依意思找相關資料", "從支援資料中找出語意接近的內容。"),
                BuilderChoice("Hybrid", "關鍵字與意思都比對", "同時使用 key/value 對照表與意思比對。"),
            ),
        ),
        BuilderStep(
            "action",
            "最後的回覆應該長什麼樣子？",
            "",
            "回覆格式",
            "",
            (
                BuilderChoice("Reply", "直接提供既有答案", "讀取指定結果 key，套用 fallback 與開頭文字。"),
                BuilderChoice("Generative", "整理成自然口吻", "沿用外部 OpenAI 相容 client 產生文字。"),
                BuilderChoice("Structured", "輸出固定格式", "沿用外部 OpenAI 相容 client 產生固定格式結果。"),
                BuilderChoice("Custom", "套用特定規則", "用規則 key/value 決定處理內容。"),
            ),
        ),
        BuilderStep(
            "reflect",
            "是否需要先檢查答案？",
            "",
            "品質檢查",
            "",
            (
                BuilderChoice("Later", "不先檢查", "不加入檢查步驟。"),
                BuilderChoice("ResponseCheck", "檢查回覆品質", "檢查答案是否回應問題，失敗處理由下方參數決定。"),
                BuilderChoice("EvidenceCheck", "檢查資料依據", "檢查執行結果與資料狀態，失敗處理由下方參數決定。"),
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
            "Recommendation": {"perceive_module": "TextPerceive", "retrieve_module": "HybridRetrieve", "action_module": "StructuredAction", "plan_strategy": "RouteBySupport"},
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
                perceive_module="StructuredPerceive",
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
            "Structured": "StructuredPerceive",
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
            updated = _replace_config(
                config,
                action_prompt=_action_prompt_from_payload(choice_label, config.action_prompt),
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
            "Structured": "StructuredAction",
            "Custom": "CustomAction",
        }.get(str(choice_label), config.action_module)
        profile_hint = _profile_hint_for_action_switch(config.profile_hint, action_module)
        workflow_name = _workflow_name_for_action_switch(config, action_module, existing_source)
        action_prompt = config.action_prompt if action_module in {"GenerativeAction", "StructuredAction"} else None
        return _build_source_for_config(
            _replace_config(
                config,
                action_module=action_module,
                profile_hint=profile_hint,
                workflow_name=workflow_name,
                action_prompt=action_prompt,
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
        updated = _replace_config(
            config,
            entry_module=_clean_allowed_value(str(choice_label.get("entry_module") or config.entry_module), _ALLOWED_ENTRY_MODULES, config.entry_module),
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


def _config_from_source(existing_source: str | None) -> BuilderSourceConfig:
    source = existing_source or build_default_python_source()
    parsed = parse_supported_source(source)
    workflow_name = parsed.workflow_name if parsed.workflow_name != "Untitled Agent" else "Customer Helper"
    action_call_name = _workflow_action_call_name(source)
    is_custom_action = bool(action_call_name and action_call_name not in {"DirectAnswerAction", "GenerativeAction", "StructuredAction"})
    task_config = _safe_config_dict(_extract_assignment_literal(source, "TASK_CONFIG", {}))
    input_config = _safe_config_dict(_extract_assignment_literal(source, "INPUT_CONFIG", {}))
    perceive_config = _safe_config_dict(_extract_assignment_literal(source, "PERCEIVE_CONFIG", {}))
    retrieve_config = _safe_config_dict(_extract_assignment_literal(source, "RETRIEVE_CONFIG", {}))
    action_config = _safe_config_dict(_extract_assignment_literal(source, "ACTION_CONFIG", {}))
    plan_config = _safe_config_dict(_extract_assignment_literal(source, "PLAN_CONFIG", {}))
    reflect_config = _safe_config_dict(_extract_assignment_literal(source, "REFLECT_CONFIG", {}))
    return BuilderSourceConfig(
        workflow_name=workflow_name,
        profile_hint=parsed.profile_hint,
        task_goal=_clean_prompt(str(task_config.get("goal", ""))),
        task_success_criteria=_clean_prompt(str(task_config.get("success_criteria", ""))),
        input_kind=str(input_config.get("kind") or _input_kind_from_source(source)),
        input_description=_clean_prompt(str(input_config.get("description", ""))),
        input_fields=tuple(_normalize_config_items(input_config.get("fields"))),
        perceive_module=_first_call_name(source, {"PassThroughPerceive", "TextPerceive", "StructuredPerceive", "TextImagePerceive"}) or "PassThroughPerceive",
        perceive_input_label=_extract_keyword_value(source, {"PassThroughPerceive"}, "input_label") or _clean_short_text(str(perceive_config.get("input_label", "")), "") or None,
        perceive_welcome_message=_extract_keyword_value(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "welcome_message"),
        perceive_options=tuple(_normalize_option_items(_extract_keyword_literal(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "options", perceive_config.get("options")))),
        perceive_importance=_extract_float_value(source, {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}, "importance", _clean_float(perceive_config.get("importance"), 1.0, 0.0, 5.0)),
        retrieve_module=_first_call_name(source, {"KeywordRetrieve", "SemanticRetrieve", "HybridRetrieve"}) or "KeywordRetrieve",
        retrieve_name=_extract_keyword_value(source, {"NextStepPlan"}, "retrieve_name") or _clean_short_text(str(retrieve_config.get("name", "支援資料")), "支援資料"),
        retrieve_description=_extract_keyword_value(source, {"NextStepPlan"}, "retrieve_description") or _clean_prompt(str(retrieve_config.get("description", ""))),
        retrieve_items=tuple(_extract_keyword_items(source)),
        retrieve_fallback=_extract_keyword_value(source, {"KeywordRetrieve", "HybridRetrieve"}, "fallback") or _clean_short_text(str(retrieve_config.get("fallback", "沒有命中任何條目。")), "沒有命中任何條目。"),
        retrieve_top_k=_extract_int_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "top_k", _clean_int(retrieve_config.get("top_k"), 3, 1, 20)),
        retrieve_similarity_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "similarity_weight", _clean_float(retrieve_config.get("similarity_weight"), 0.5, 0.0, 1.0)),
        retrieve_recency_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "recency_weight", _clean_float(retrieve_config.get("recency_weight"), 0.3, 0.0, 1.0)),
        retrieve_importance_weight=_extract_float_value(source, {"SemanticRetrieve", "HybridRetrieve"}, "importance_weight", _clean_float(retrieve_config.get("importance_weight"), 0.2, 0.0, 1.0)),
        action_module="CustomAction" if is_custom_action else action_call_name or "DirectAnswerAction",
        action_prompt=_extract_keyword_value(source, {"GenerativeAction", "StructuredAction"}, "system_prompt") or _clean_prompt(str(action_config.get("output_guidance", ""))) or None,
        direct_answer_memory_key=_clean_allowed_value(_extract_keyword_value(source, {"DirectAnswerAction"}, "memory_key") or str(action_config.get("direct_memory_key", "latest_retrieved_content")), _ALLOWED_DIRECT_RESULT_KEYS, "latest_retrieved_content"),
        direct_answer_fallback=_extract_keyword_value(source, {"DirectAnswerAction"}, "fallback") or _clean_short_text(str(action_config.get("direct_fallback", "沒有命中任何條目。")), "沒有命中任何條目。"),
        direct_answer_prefix=_extract_keyword_value(source, {"DirectAnswerAction"}, "prefix") or _clean_short_text(str(action_config.get("direct_prefix", "")), ""),
        custom_action_class=action_call_name if is_custom_action else "BusinessRule",
        custom_action_memory_key=_extract_assignment_value(source, "CUSTOM_ACTION_MEMORY_KEY", "latest_retrieved_content"),
        custom_action_fallback=_extract_assignment_value(source, "CUSTOM_ACTION_FALLBACK", "找不到符合的支援資料。"),
        custom_action_prefix=_extract_assignment_value(source, "CUSTOM_ACTION_PREFIX", "自訂處理結果："),
        custom_rule_title=_extract_assignment_value(source, "BUSINESS_RULE_TITLE", "作業規則"),
        custom_rule_instruction=_extract_assignment_value(source, "BUSINESS_RULE_INSTRUCTION", "") or None,
        plan_strategy="RouteBySupport" if "NextStepPlan(" in source else None,
        plan_direct_rule=_clean_prompt(str(plan_config.get("direct_rule", ""))),
        plan_system_prompt=_extract_keyword_value(source, {"NextStepPlan"}, "system_prompt") or _clean_prompt(str(plan_config.get("route_rule", ""))) or None,
        reflect_module=_first_call_name(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}),
        reflect_on_failure=_extract_keyword_value(source, {"ResponseCheckReflect", "EvidenceCheckReflect"}, "on_failure"),
        reflect_criteria=_clean_prompt(str(reflect_config.get("criteria", ""))),
        entry_module=_clean_allowed_value(_extract_keyword_value(source, {"Workflow"}, "entry_module") or "perceive", _ALLOWED_ENTRY_MODULES, "perceive"),
        max_node_hops=_extract_int_value(source, {"Gates"}, "max_node_hops", 50),
        max_revisit=_extract_int_value(source, {"Gates"}, "max_revisit", 5),
        timeout_sec=_extract_float_value(source, {"Gates"}, "timeout_sec", 300.0),
    )


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
        "StructuredPerceive": "Structured",
        "TextImagePerceive": "TextImage",
    }.get(config.perceive_module, "Simple")
    retrieve_choice = {
        "SemanticRetrieve": "Semantic",
        "HybridRetrieve": "Hybrid",
    }.get(config.retrieve_module, "Keyword" if config.retrieve_items else "None yet")
    action_choice = {
        "DirectAnswerAction": "Reply",
        "GenerativeAction": "Generative",
        "StructuredAction": "Structured",
        "CustomAction": "Custom",
    }.get(config.action_module, "Reply")
    reflect_choice = {
        "ResponseCheckReflect": "ResponseCheck",
        "EvidenceCheckReflect": "EvidenceCheck",
    }.get(config.reflect_module or "", "Later")

    return {
        "template": template_choice,
        "input": config.input_kind,
        "perceive": perceive_choice,
        "plan": "RouteBySupport" if config.plan_strategy else "Direct",
        "retrieve": retrieve_choice,
        "action": action_choice,
        "reflect": reflect_choice,
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
    if action_module == "StructuredAction":
        return "Structured Result"
    if action_module == "CustomAction":
        return "Custom Action"
    if current_profile_hint in _ACTION_SPECIFIC_PROFILE_HINTS:
        return None
    return current_profile_hint


def _workflow_name_for_action_switch(config: BuilderSourceConfig, action_module: str, existing_source: str | None) -> str:
    if action_module == "StructuredAction":
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
    if {"formal_audience", "formal_structure", "formal_constraints"} & keys:
        return _formal_response_prompt(payload)
    if {"reply_style", "response_shape"} & keys:
        return _advisor_action_prompt(payload)
    if "output_guidance" in payload:
        return _clean_prompt(str(payload.get("output_guidance", "")))
    if "system_prompt" in payload:
        return _clean_prompt(str(payload.get("system_prompt", "")))
    return current_prompt


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
    if "StructuredPerceive(" in python_source:
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
    hint = f"# Playground V2 profile hint: {config.profile_hint}\n" if config.profile_hint else ""
    needs_openai_client = _needs_openai_client(config)
    module_names = [config.retrieve_module, config.perceive_module, _action_class_for_config(config)]
    if config.plan_strategy:
        module_names.append("NextStepPlan")
    if config.reflect_module:
        module_names.append(config.reflect_module)
    import_block = _format_module_imports(module_names)
    openai_block = _openai_client_block(config) if needs_openai_client else ""
    plan_line = _plan_line(config) if config.plan_strategy else ""
    reflect_line = _reflect_line(config) if config.reflect_module else ""
    return f"""{_openai_import(needs_openai_client)}from agentic_sdk import Workflow
from agentic_sdk import Gates
{import_block}

{openai_block}{hint}workflow = Workflow(
    workflow_name={workflow_name_literal},
    gates=Gates(max_node_hops={config.max_node_hops}, max_revisit={config.max_revisit}, timeout_sec={config.timeout_sec}),
    entry_module={json.dumps(config.entry_module, ensure_ascii=False)},
    perceive={_perceive_expression(config)},
{plan_line}    retrieve={config.retrieve_module}(
{_retrieve_expression_body(config)}
    ),
{reflect_line}    action={_action_expression(config)},
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
    needs_openai_client = bool(config.plan_strategy or config.reflect_on_failure)
    module_names = [config.retrieve_module, config.perceive_module]
    if config.plan_strategy:
        module_names.append("NextStepPlan")
    if config.reflect_module:
        module_names.append(config.reflect_module)
    import_block = _format_module_imports(module_names)
    openai_block = _openai_client_block(config) if needs_openai_client else ""
    plan_line = _plan_line(config) if config.plan_strategy else ""
    reflect_line = _reflect_line(config) if config.reflect_module else ""
    return f"""{_openai_import(needs_openai_client)}from agentic_sdk import Workflow
from agentic_sdk import Gates
{import_block}

{openai_block}CUSTOM_ACTION_MEMORY_KEY = {memory_key_literal}
CUSTOM_ACTION_FALLBACK = {fallback_literal}
CUSTOM_ACTION_PREFIX = {prefix_literal}
BUSINESS_RULE_TITLE = {rule_title_literal}
BUSINESS_RULE_INSTRUCTION = {rule_instruction_literal}


class {custom_action_class}:
    def __call__(self, memory):
        summary = memory.lookup(CUSTOM_ACTION_MEMORY_KEY) or CUSTOM_ACTION_FALLBACK
        if BUSINESS_RULE_INSTRUCTION:
            return f"{{CUSTOM_ACTION_PREFIX}}{{summary}}\\n\\n{{BUSINESS_RULE_TITLE}}：{{BUSINESS_RULE_INSTRUCTION}}"
        return f"{{CUSTOM_ACTION_PREFIX}}{{summary}}"


# Playground V2 profile hint: Custom Action
workflow = Workflow(
    workflow_name={workflow_name_literal},
    gates=Gates(max_node_hops={config.max_node_hops}, max_revisit={config.max_revisit}, timeout_sec={config.timeout_sec}),
    entry_module={json.dumps(config.entry_module, ensure_ascii=False)},
    perceive={_perceive_expression(config)},
{plan_line}    retrieve={config.retrieve_module}(
{_retrieve_expression_body(config)}
    ),
{reflect_line}    action={custom_action_class}(),
)
"""


def _needs_openai_client(config: BuilderSourceConfig) -> bool:
    return bool(
        config.perceive_module in {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}
        or config.action_module in {"GenerativeAction", "StructuredAction"}
        or config.plan_strategy
        or config.reflect_module == "ResponseCheckReflect"
    )


def _action_class_for_config(config: BuilderSourceConfig) -> str:
    if config.action_module == "StructuredAction":
        return "StructuredAction"
    if config.action_module == "GenerativeAction":
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
    return f"{action_class}({', '.join(_llm_arguments('ACTION'))})"


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
        f"api_key={prefix}_API_KEY",
        f"base_url={prefix}_API_BASE_URL",
        f"model={prefix}_MODEL",
    ]


def _llm_env_prefixes(config: BuilderSourceConfig) -> list[str]:
    prefixes: list[str] = []
    if config.perceive_module in {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}:
        prefixes.append("PERCEIVE")
    if config.plan_strategy:
        prefixes.append("PLAN")
    if config.action_module in {"GenerativeAction", "StructuredAction"}:
        prefixes.append("ACTION")
    if config.reflect_module == "ResponseCheckReflect":
        prefixes.append("REFLECT")
    return prefixes


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


def _openai_import(needs_openai_client: bool) -> str:
    return "import os\n\n" if needs_openai_client else ""


def _openai_client_block(config: BuilderSourceConfig) -> str:
    lines: list[str] = []
    for prefix in _llm_env_prefixes(config):
        lines.extend(
            [
                f'{prefix}_API_KEY = os.environ["{prefix}_API_KEY"]',
                f'{prefix}_API_BASE_URL = os.environ["{prefix}_API_BASE_URL"]',
                f'{prefix}_MODEL = os.environ["{prefix}_MODEL"]',
            ]
        )
    return "\n".join(lines) + "\n\n"


def _format_module_imports(module_names: list[str]) -> str:
    ordered_names = [
        name
        for name in (
            "DirectAnswerAction",
            "GenerativeAction",
            "EvidenceCheckReflect",
            "StructuredAction",
            "KeywordRetrieve",
            "SemanticRetrieve",
            "HybridRetrieve",
            "NextStepPlan",
            "PassThroughPerceive",
            "TextPerceive",
            "StructuredPerceive",
            "TextImagePerceive",
            "ResponseCheckReflect",
        )
        if name in set(module_names)
    ]
    return "from agentic_sdk.modules import (\n    " + ",\n    ".join(ordered_names) + ",\n)"


def _format_python_literal(value: object, continuation_indent: int) -> str:
    literal = json.dumps(value, ensure_ascii=False, indent=4)
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