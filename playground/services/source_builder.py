from __future__ import annotations

import ast
import keyword
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_sdk.defaults import DEFAULT_NO_MATCHING_ENTRIES_MESSAGE, DEFAULT_RETRIEVED_CONTENT_KEY, SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH
from playground.models import BuilderChoice, BuilderStep, WorkflowSummary
from playground.services.workflow_reachability import reachable_workflow_roles


DEFAULT_WORKFLOW_NAME = "default"
GENERATED_WORKFLOW_NAMES = {DEFAULT_WORKFLOW_NAME}

ALLOWED_DIRECT_RESULT_KEYS = {
    "latest_retrieved_content",
    "retrieved_snippet",
    "perceived_input",
    "query",
    "latest_final_message",
}
ALLOWED_ENTRY_MODULES = {"perceive", "plan", "retrieve", "action"}
_OUTPUT_FORMAT_PROMPTS = {
    "free_text": "請依使用者需求自然回覆；語氣、角色與回覆方式以使用者設定的回覆風格與規範為準。",
    "interactive": "請同時支援純文字回覆與 OpenAI tool calling。一般問題可自然回答；當需要使用者選擇或填寫資料時，請呼叫最符合的工具，不要把 component/api JSON 當成一般文字輸出。",
    "natural": "請用自然語句回覆；先給結論，再補必要依據與下一步。",
    "bullets": "請用條列摘要回覆；依序列出結論、依據、下一步。",
    "table": "請用表格呈現結果；欄位要清楚，內容要可比較。",
    "json": "請輸出 JSON；欄位固定、值簡潔，不要加入 JSON 以外的文字。",
    "custom_schema": "請依指定格式輸出；欄位缺資料時使用空字串或明確標註未知。",
}
INTERACTIVE_TOOL_POLICY = """互動元件使用原則：
以下是內部決策規則，不要向使用者描述判斷、工具或元件流程。先在內部判斷使用者這一輪的意圖類型，而不是因為已配置互動元件就要求使用者選擇。
當使用者只是詢問資訊、要求分析、要求解釋、比較原因、了解現況或追問依據時，只用自然語言回答，不要提出確認問題。
只有當使用者明確進入決策、確認、提交、申請、送出表單、安排後續流程或選擇下一步，且該需求符合工具描述時，才提出互動確認。
互動確認只能收集該工具 schema 中定義的欄位；不可自行要求、暗示或臆測未配置的業務欄位。若 required 欄位尚未齊全，只簡潔要求缺少的 schema 欄位；全部齊全後才呼叫工具。
需要互動確認時，對使用者直接輸出建議、必要依據、限制與下一步，最後用自然語言提出清楚的確認問題；Playground 會依配置顯示互動元件並收集使用者選擇。
不要把 API URL、component schema、欄位 JSON 或內部工具設定當成使用者可見文字輸出。"""
FREE_TEXT_OUTPUT_CHOICES = {"free_text", "natural", "bullets"}
INTERACTIVE_OUTPUT_CHOICES = {"interactive", "table", "json", "custom_schema"}
TOOL_CALL_OUTPUT_CHOICES = {"interactive"}
# Answering with what was looked up, without a model in the loop. The module
# has always existed and the README opens with it; Q4 just never offered it,
# so an agent built on a lookup table had to buy a model call it did not need.
DIRECT_ANSWER_OUTPUT_CHOICES = {"direct"}
VOICE_OUTPUT_CHOICES = {"voice"}
STRUCTURED_OUTPUT_CHOICES = {"table", "json", "custom_schema"}
DEFAULT_RETRIEVE_DESCRIPTION = "依使用者設定的關鍵字參考資料判斷是否需要查詢。"
DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION = "依上傳的參考文件查找與問題最相關的內容。"
DEFAULT_RUNNER_DESCRIPTION = "可填寫這個 Agent 的用途、適用情境或回覆目標。"
_PLAYGROUND_REVIEW_FIELD = "__playground_review"
_PLAYGROUND_OPTIONS_FIELD = "__playground_options"
AUDIO_TRANSPORT_NAME = "transcription"
SPEECH_OUTPUT_NAME = "speech"

_MODULE_IMPORT_ORDER = (
    "PassThroughPerceive",
    "TextPerceive",
    "TextImagePerceive",
    "VoiceTextPerceive",
    "NextStepPlan",
    "PassThroughPlan",
    "PassThroughRetrieve",
    "KeywordRetrieve",
    "SemanticRetrieve",
    "EvidenceCheckReflect",
    "PlanCheckReflect",
    "DirectAnswerAction",
    "GenerativeAction",
    "ToolCallAction",
    "VoiceAnswerAction",
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
    action_tool_choice: str | dict[str, object] | None = None
    direct_answer_memory_key: str = "latest_retrieved_content"
    direct_answer_fallback: str = "沒有命中任何條目。"
    direct_answer_prefix: str = ""
    custom_action_class: str = "BusinessRule"
    custom_action_memory_key: str = "latest_retrieved_content"
    custom_action_fallback: str = "找不到符合的參考資料。"
    custom_action_prefix: str = "自訂處理結果："
    custom_rule_title: str = "處理規則"
    custom_rule_instruction: str | None = None
    plan_strategy: str | None = None
    plan_system_prompt: str | None = None
    reflect_module: str | None = None
    reflect_on_failure: str | None = None
    entry_module: str = "perceive"
    events_schema: dict[str, dict[str, object]] | None = None
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
                # Locked on purpose: it shows where CrossContextMemory is going.
                # Removing it removes the roadmap, not a broken feature.
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
                BuilderChoice("voice", "語音對話", "使用者用講的，安靜時不會傳送任何聲音。轉寫結果直接交給後續步驟。"),
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
                BuilderChoice("semantic", "語意搜尋", "依意思找最相關的參考資料。"),
            ),
        ),
        BuilderStep(
            "output_format",
            "Q4: 最後回覆要怎麼呈現給使用者？",
            "",
            "回覆呈現",
            "",
            (
                BuilderChoice("free_text", "純文字回覆", "設定 Agent 的角色、語氣、回答順序與限制。"),
                BuilderChoice("interactive", "可互動元件", "沿用同一組回覆風格與規範，再追加抽取欄位與 API 提交規格。"),
                BuilderChoice("direct", "直接回傳查到的內容", "把查到的內容原樣回覆，不經過模型改寫。查不到時回覆你設定的備援字句。"),
                BuilderChoice("voice", "語音回覆", "一邊在畫面上給精確資料，一邊用口語講重點，兩者互補而不是把畫面唸一遍。"),
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


def pairs_text_from_options(options: tuple[dict[str, object], ...]) -> str:
    return "\n".join(
        f"{str(option.get('label', '')).strip()} = {str(option.get('intent', '')).strip()}"
        for option in options
        if str(option.get("label", "")).strip() and str(option.get("intent", "")).strip()
    )


def lines_text_from_items(items: tuple[str, ...]) -> str:
    return "\n".join(item for item in items if item)


def pairs_text_from_retrieve_items(items: tuple[dict[str, object], ...]) -> str:
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


def response_instruction_from_prompt(prompt: str | None) -> str | None:
    return _user_authored_action_prompt(prompt)


def api_contracts_json_from_tools(tools: tuple[dict[str, object], ...]) -> str | None:
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
        if name in {_PLAYGROUND_REVIEW_FIELD, _PLAYGROUND_OPTIONS_FIELD}:
            continue
        if not isinstance(field, dict):
            continue
        label = clean_short_text(str(name), "")
        description = clean_prompt(str(field.get("description") or "")) or label
        json_type = type_labels.get(str(field.get("type") or "string").lower(), "文字")
        if label and description:
            lines.append(f"{label} = {description}（資料類型：{json_type}）")
    return "\n".join(lines)


def string_items_from_lines(value: str) -> list[str]:
    return [item for item in (line.strip() for line in value.splitlines()) if item]


def clean_workflow_name(workflow_name: str) -> str:
    return " ".join(workflow_name.split()).strip()[:64]


def clean_prompt(prompt: str) -> str | None:
    cleaned = "\n".join(line.rstrip() for line in prompt.strip().splitlines()).strip()
    return cleaned[:500] or None


def clean_short_text(value: str, fallback: str) -> str:
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


def clean_allowed_value(value: str, allowed_values: set[str], fallback: str) -> str:
    cleaned = value.strip()
    return cleaned if cleaned in allowed_values else fallback


def action_prompt_from_payload(payload: dict[str, Any], current_prompt: str | None) -> str | None:
    if "response_instruction" in payload:
        return clean_prompt(str(payload.get("response_instruction", "")))
    return _user_authored_action_prompt(current_prompt)


def payload_has_interactive_contract(payload: dict[str, Any]) -> bool:
    return bool({"interaction_trigger", "api_method", "api_url", "component_fields", "api_contracts"} & set(payload))


def fixed_format_action_prompt_from_payload(payload: dict[str, Any], current_prompt: str | None) -> str | None:
    if not ({"rule_title", "rule_pairs"} & set(payload)):
        return current_prompt
    title = clean_short_text(str(payload.get("rule_title", "")), "")
    rules = _rule_instruction_from_pairs(str(payload.get("rule_pairs", "")))
    if not title and not rules:
        return current_prompt
    parts = [current_prompt or _OUTPUT_FORMAT_PROMPTS["custom_schema"]]
    if title:
        parts.append(f"格式名稱：{title}")
    if rules:
        parts.append(f"固定欄位或規則：\n{rules}")
    return "\n".join(parts)


def retrieve_items_from_payload(payload: dict[str, Any]) -> tuple[dict[str, object], ...]:
    pair_items = _retrieve_pair_items_from_text(str(payload.get("keyword_pairs", "")))
    if pair_items:
        return tuple(pair_items)

    keywords = _split_keywords(str(payload.get("keywords", "")))
    content = clean_prompt(str(payload.get("content", "")))
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
        content = clean_prompt(value)
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
        config_key = clean_short_text(key, "")
        config_value = clean_short_text(value, "")
        if config_key and config_value:
            items.append({"key": config_key, "value": config_value})
    return items[:20]


def option_items_from_pairs(raw_pairs: str) -> list[dict[str, object]]:
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
        rule_key = clean_short_text(key, "")
        rule_value = clean_prompt(value)
        if rule_key and rule_value:
            rules.append(f"{rule_key}：{rule_value}")
    return "\n".join(rules[:20]) or None


def tools_from_action_payload(payload: dict[str, Any]) -> tuple[dict[str, object], ...]:
    tools = []
    for index, contract in enumerate(_interactive_api_contracts(payload), start=1):
        fields = _tool_parameters_from_pairs(str(contract.get("component_fields") or ""))
        if not fields["properties"]:
            continue
        api_method = str(contract.get("api_method") or "POST")
        api_url = str(contract.get("api_url") or "")
        trigger = str(contract.get("interaction_trigger") or "")
        description_parts = ["顯示互動元件並收集使用者選擇。", trigger]
        if api_url:
            description_parts.append(f"API：{api_method} {api_url}")
        description = " ".join(part for part in description_parts if part).strip() or "提交 API 所需資料。"
        fields["properties"][_PLAYGROUND_REVIEW_FIELD] = {
            "type": "string",
            "description": "平台顯示用確認摘要。只列出本輪已知事實與必要限制，例如安排、商品、時間、供應或缺口；不要提問、不要寫待確認事項、不要重述任何表單欄位或選項。表單本身會提出唯一需要使用者決定的問題。不要把它當成使用者輸入，也不要要求使用者編輯。",
        }
        fields["required"].append(_PLAYGROUND_REVIEW_FIELD)
        fields["properties"][_PLAYGROUND_OPTIONS_FIELD] = {
            "type": "object",
            "description": "平台顯示用文字選項。針對每個資料類型為文字的欄位，以該欄位名稱為 key，提供 choices（1 到 4 個簡短且具體的建議選項字串）和 custom_label（使用者自行填寫時的按鈕標籤）。choices 第一個必須是最推薦的選項，且同時填入該文字欄位作為預設值。只提供文字欄位的 key，不要包含是/否、數字或平台保留欄位。不要把它當成使用者輸入。",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "choices": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                    "custom_label": {"type": "string"},
                },
                "required": ["choices", "custom_label"],
                "additionalProperties": False,
            },
        }
        fields["required"].append(_PLAYGROUND_OPTIONS_FIELD)
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
        key = clean_short_text(raw_key, "")
        description, json_type = _field_description_and_json_type(raw_value)
        if not key or key in properties:
            continue
        properties[key] = {"type": json_type, "description": description or key}
        if not _is_optional_tool_field(description):
            required.append(key)
    return {"properties": properties, "required": required}


def _is_optional_tool_field(description: str) -> bool:
    normalized = str(description or "").lower()
    return any(marker in normalized for marker in ("可留空", "選填", "非必填", "optional"))


def _field_description_and_json_type(raw_value: str) -> tuple[str, str]:
    value = str(raw_value).strip()
    json_type = "string"
    marker = "（資料類型："
    if marker in value and value.endswith(("）", ")")):
        value, raw_type = value.rsplit(marker, 1)
        normalized_type = raw_type.removesuffix("）").removesuffix(")").strip().lower()
        if "number" in normalized_type or "數字" in normalized_type:
            json_type = "number"
        elif "boolean" in normalized_type or "是/否" in normalized_type:
            json_type = "boolean"
    return (clean_prompt(value) or "", json_type)


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


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def build_source_for_config(config: BuilderSourceConfig) -> str:
    if config.profile_hint == "Custom Action" or config.action_module == "CustomAction":
        return _build_custom_action_source(config)
    return _build_workflow_source(config)


def _build_workflow_source(config: BuilderSourceConfig) -> str:
    workflow_name_literal = json.dumps(config.workflow_name, ensure_ascii=False)
    reachable_roles = reachable_workflow_roles(config)
    workflow_arguments = _workflow_argument_lines(
        config,
        reachable_roles,
        action_expression=_action_expression(config),
    )
    workflow_metadata_lines = [f"    workflow_name={workflow_name_literal},"]
    if config.task_goal:
        workflow_metadata_lines.append(f"    description={json.dumps(config.task_goal, ensure_ascii=False)},")
    workflow_block = f"""workflow = Workflow(
{chr(10).join(workflow_metadata_lines)}
{workflow_arguments}
)"""
    import_block = _format_module_imports(_module_names_for_source(workflow_block))
    import_lines = [_core_import_line()]
    if import_block:
        import_lines.append(import_block)
    sections = ["\n".join(import_lines)]
    audio_section = _audio_transport_section(workflow_block)
    if audio_section:
        sections.append(audio_section)
    sections.append(workflow_block)
    return "\n\n".join(sections) + "\n"


def _build_custom_action_source(config: BuilderSourceConfig) -> str:
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
    )
    workflow_metadata_lines = [f"    workflow_name={workflow_name_literal},"]
    if config.task_goal:
        workflow_metadata_lines.append(f"    description={json.dumps(config.task_goal, ensure_ascii=False)},")
    workflow_block = f"""class {custom_action_class}:
    name = "action"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        summary = state.lookup({memory_key_literal}) or {fallback_literal}
        instruction = {rule_instruction_literal}
        if instruction:
            content = {prefix_literal} + summary + "\\n\\n" + {rule_title_literal} + "：" + instruction
        else:
            content = {prefix_literal} + summary
        return ModuleOutput(
            next_module=None,
            payload={{"latest_final_message": content}},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.ACTION_RESULT,
                    content=content,
                    metadata={{"source": {json.dumps(custom_action_class, ensure_ascii=False)}}},
                )
            ],
        )

workflow = Workflow(
{chr(10).join(workflow_metadata_lines)}
{workflow_arguments}
)
"""
    import_block = _format_module_imports(_module_names_for_source(workflow_block))
    import_lines = [
        _core_import_line(),
        "from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState",
    ]
    if import_block:
        import_lines.append(import_block)
    sections = ["# Playground profile hint: Custom Action", "\n".join(import_lines)]
    sections.append(workflow_block)
    return "\n\n".join(sections) + "\n"


def _core_import_line() -> str:
    return "from agentic_sdk import Workflow"


def _workflow_argument_lines(
    config: BuilderSourceConfig,
    reachable_roles: set[str],
    *,
    action_expression: str,
) -> str:
    lines: list[str] = []
    if config.events_schema is not None:
        lines.append(f"    events_schema={_format_python_literal(config.events_schema, 4)},")
    if "perceive" in reachable_roles:
        lines.append(f"    perceive={_perceive_expression(config)},")
    if "plan" in reachable_roles:
        lines.append(_plan_line(config, reachable_roles).rstrip("\n"))
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
    if config.action_module == "GenerativeAction":
        return "GenerativeAction"
    if config.action_module == "VoiceAnswerAction":
        return "VoiceAnswerAction"
    return "DirectAnswerAction"


def _action_expression(config: BuilderSourceConfig) -> str:
    action_class = _action_class_for_config(config)
    if action_class == "DirectAnswerAction":
        arguments = []
        if config.direct_answer_memory_key != DEFAULT_RETRIEVED_CONTENT_KEY:
            arguments.append(f"memory_key={json.dumps(config.direct_answer_memory_key, ensure_ascii=False)}")
        if config.direct_answer_fallback != DEFAULT_NO_MATCHING_ENTRIES_MESSAGE:
            arguments.append(f"fallback={json.dumps(config.direct_answer_fallback, ensure_ascii=False)}")
        if config.direct_answer_prefix:
            arguments.append(f"prefix={json.dumps(config.direct_answer_prefix, ensure_ascii=False)}")
        return f"DirectAnswerAction({', '.join(arguments)})" if arguments else "DirectAnswerAction()"
    arguments = _llm_arguments(binding_role="action")
    if action_class == "VoiceAnswerAction":
        # 播音的物件在外部建立後傳進來，不是端點設定的一部分 —— 見 ADR-0003。
        arguments.insert(0, f"speech={SPEECH_OUTPUT_NAME}")
    action_prompt = _action_system_prompt_for_config(config, action_class)
    if action_prompt:
        arguments.append(f"system_prompt={json.dumps(action_prompt, ensure_ascii=False)}")
    if action_class == "ToolCallAction" and config.action_tools:
        arguments.append(f"tools={_format_python_literal(list(config.action_tools), 8)}")
        if config.action_tool_choice is not None:
            arguments.append(f"tool_choice={_format_python_literal(config.action_tool_choice, 8)}")
    return f"{action_class}({', '.join(arguments)})"


def _action_system_prompt_for_config(config: BuilderSourceConfig, action_class: str) -> str | None:
    if action_class != "ToolCallAction":
        return config.action_prompt
    if config.action_prompt:
        return f"{INTERACTIVE_TOOL_POLICY}\n\n使用者設定的回覆規範：\n{config.action_prompt}"
    return INTERACTIVE_TOOL_POLICY


def _perceive_expression(config: BuilderSourceConfig) -> str:
    if config.perceive_module == "PassThroughPerceive":
        if config.perceive_input_label:
            return f"PassThroughPerceive(input_label={json.dumps(config.perceive_input_label, ensure_ascii=False)})"
        return "PassThroughPerceive()"
    if config.perceive_module == "VoiceTextPerceive":
        # 收音的物件同樣在外部建立，且它不是聊天端點，吃不下那三個參數。
        return f"VoiceTextPerceive(transport={AUDIO_TRANSPORT_NAME})"
    arguments = _llm_arguments(binding_role="perceive")
    if config.perceive_welcome_message:
        arguments.append(f"welcome_message={json.dumps(config.perceive_welcome_message, ensure_ascii=False)}")
    if config.perceive_options:
        arguments.append(f"options={_format_python_literal(list(config.perceive_options), 8)}")
    if config.perceive_module == "TextImagePerceive" and config.perceive_image_instruction:
        arguments.append(f"image_instruction={json.dumps(config.perceive_image_instruction, ensure_ascii=False)}")
    return f"{config.perceive_module}({', '.join(arguments)})"


def _retrieve_expression_body(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "KeywordRetrieve":
        if config.retrieve_items:
            return f"        items={_format_python_literal(list(config.retrieve_items), 14)},"
        return ""
    if config.retrieve_module == "PassThroughRetrieve":
        return ""
    arguments = [f"        {argument}," for argument in _llm_arguments(binding_role="retrieve")]
    source_paths = _semantic_source_paths(config)
    if source_paths:
        arguments.append(f"        sources={_format_python_literal(source_paths, 16)},")
    return "\n".join(arguments)


def _plan_line(config: BuilderSourceConfig, reachable_roles: set[str]) -> str:
    # Named even when nobody chose one, so a reader of the code sees that every
    # run passes through planning — see ADR-0005.
    if not config.plan_strategy:
        return "    plan=PassThroughPlan(),\n"
    description = _explicit_retrieve_description(config)
    plan_binding_role = "action" if "action" in reachable_roles else "perceive"
    arguments = [
        *_llm_arguments(binding_role=plan_binding_role),
    ]
    if description:
        arguments.append(f"retrieve_description={json.dumps(description, ensure_ascii=False)}")
    return f"    plan=NextStepPlan({', '.join(arguments)}),\n"


def _reflect_line(config: BuilderSourceConfig) -> str:
    reflect_module = config.reflect_module or "PlanCheckReflect"
    arguments = _llm_arguments(binding_role="reflect") if reflect_module == "PlanCheckReflect" else []
    return (
        f"    reflect={reflect_module}("
        f"{', '.join(arguments)}"
        "),\n"
    )


def _llm_arguments(*, binding_role: str | None = None) -> list[str]:
    model_argument = "embedding_model" if binding_role == "retrieve" else "model"
    return [
        'api_key="<API_KEY>"',
        'base_url="<BASE_URL>"',
        f'{model_argument}="<MODEL>"',
    ]


def retrieve_description(config: BuilderSourceConfig) -> str:
    if config.retrieve_module == "SemanticRetrieve":
        if config.semantic_search_goal:
            return f"優先從這批參考文件查找：{config.semantic_search_goal}"[:240]
        if config.retrieve_description:
            return config.retrieve_description[:240]
        return DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION
    if config.retrieve_description:
        return config.retrieve_description[:240]
    if config.retrieve_items:
        content = str(config.retrieve_items[0].get("content", "")).strip()
        if content:
            return content[:120]
    return DEFAULT_RETRIEVE_DESCRIPTION


def _explicit_retrieve_description(config: BuilderSourceConfig) -> str | None:
    if config.semantic_search_goal:
        return retrieve_description(config)
    if config.retrieve_description and config.retrieve_description not in {DEFAULT_RETRIEVE_DESCRIPTION, DEFAULT_SEMANTIC_RETRIEVE_DESCRIPTION}:
        return retrieve_description(config)
    if config.retrieve_items:
        content = str(config.retrieve_items[0].get("content", "")).strip()
        return content[:120] if content else None
    return None


def _semantic_source_paths(config: BuilderSourceConfig) -> list[str]:
    if not config.semantic_support_files:
        return []
    return [f"./{Path(filename).name}" for filename in config.semantic_support_files]


def _format_module_imports(module_names: list[str]) -> str:
    ordered_names = [name for name in _MODULE_IMPORT_ORDER if name in set(module_names)]
    if not ordered_names:
        return ""
    return "from agentic_sdk.modules import (\n    " + ",\n    ".join(ordered_names) + ",\n)"


def _audio_transport_section(workflow_block: str) -> str | None:
    """Build the two audio objects a voice workflow is handed.

    They sit above the workflow rather than inside it because audio sources are
    not interchangeable the way chat endpoints are, so the SDK takes an object
    and never a vendor name — see ADR-0003. Swapping vendor means overriding one
    method on these two classes, which is why they are named here at all.
    """
    lines: list[str] = []
    imports: list[str] = []
    if f"transport={AUDIO_TRANSPORT_NAME}" in workflow_block:
        imports.append("RealtimeTranscription")
        lines.append(
            f'{AUDIO_TRANSPORT_NAME} = RealtimeTranscription('
            'api_key="<API_KEY>", base_url="<BASE_URL>", model="<MODEL>")'
        )
    if f"speech={SPEECH_OUTPUT_NAME}" in workflow_block:
        imports.append("SpeechOutput")
        lines.append(
            f'{SPEECH_OUTPUT_NAME} = SpeechOutput('
            'api_key="<API_KEY>", base_url="<BASE_URL>", model="<MODEL>")'
        )
    if not lines:
        return None
    return "\n".join([f"from agentic_sdk.audio import {', '.join(imports)}", "", *lines])


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
    cleaned = clean_prompt(str(prompt or ""))
    if not cleaned:
        return None
    if cleaned == INTERACTIVE_TOOL_POLICY:
        return None
    if cleaned.startswith(f"{INTERACTIVE_TOOL_POLICY}\n\n使用者設定的回覆規範：\n"):
        cleaned = cleaned.split("使用者設定的回覆規範：\n", 1)[1].strip()
    if cleaned in _OUTPUT_FORMAT_PROMPTS.values():
        return None
    return cleaned


def _format_python_literal(value: object, continuation_indent: int) -> str:
    literal = json.dumps(value, ensure_ascii=False, indent=4)
    literal = literal.replace(": false", ": False").replace(": true", ": True").replace(": null", ": None")
    return literal.replace("\n", "\n" + " " * continuation_indent)


def get_workflow_summary(spec: dict) -> WorkflowSummary:
    """Summarise an agent spec for the Builder and Runner headers.

    The template variants this used to select came from a profile-hint comment
    in the compiled source. A spec carries no hint, so every agent reports the
    one template.
    """
    return WorkflowSummary(
        name=str(spec.get("workflow_name") or "default"),
        input_contract="輸入規格：使用者內容",
        output_contract="輸出規格：回覆內容",
        template="回覆助理",
        readiness="可開始使用",
        can_run=True,
        can_roundtrip=True,
    )


def _interactive_api_contracts(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    raw_contracts = str(payload.get("api_contracts", "") or "").strip()
    contracts: list[dict[str, str | None]] = []
    if not raw_contracts:
        direct_fields = _rule_instruction_from_pairs(str(payload.get("component_fields", "")))
        direct_trigger = clean_prompt(str(payload.get("interaction_trigger", "")))
        direct_api_method = clean_short_text(str(payload.get("api_method", "POST")), "POST").upper()
        direct_api_url = clean_prompt(str(payload.get("api_url", "")))
        if direct_trigger or direct_api_url or direct_fields:
            return [
                {
                    "interaction_trigger": direct_trigger,
                    "api_method": direct_api_method,
                    "api_url": direct_api_url,
                    "component_fields": direct_fields,
                }
            ]
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
        trigger = clean_prompt(str(contract.get("interaction_trigger", "")))
        api_method = clean_short_text(str(contract.get("api_method", "POST")), "POST").upper()
        api_url = clean_prompt(str(contract.get("api_url", "")))
        if trigger or api_url or fields:
            contracts.append({
                "interaction_trigger": trigger,
                "api_method": api_method,
                "api_url": api_url,
                "component_fields": fields,
            })
    return contracts