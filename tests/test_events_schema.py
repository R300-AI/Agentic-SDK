from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agentic_sdk import (
    GenerativeAction,
    Gates,
    ModuleSpec,
    NextStepPlan,
    PassThroughRetrieve,
    ResponseCheckReflect,
    TextPerceive,
    Workflow,
    WorkflowConfig,
    build_workflow,
)
from agentic_sdk.llm.openai_compatible import IncrementalJsonFieldParser
from agentic_sdk.llm.openai_compatible import OpenAIChatResponse

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}

EVENTS_SCHEMA = {
    "perceive": {
        "label": "理解輸入",
        "fields": ["summary", "details.next_step"],
    },
    "plan": {
        "label": "判斷工具順序",
        "fields": ["thought", "next_module"],
    },
    "action": {
        "label": "準備輸出回覆",
    },
}
DEFAULT_LABELS = {
    "perceive": "理解輸入",
    "plan": "判斷工具順序",
    "retrieve": "整理相關來源",
    "action": "準備輸出回覆",
    "reflect": "檢查回覆",
}


def test_incremental_json_field_parser_handles_escaped_values_and_chunk_boundaries() -> None:
    emitted: list[tuple[str, object]] = []
    parser = IncrementalJsonFieldParser(
        ["summary", "details.next_step"],
        lambda field, value: emitted.append((field, value)),
    )
    payload = json.dumps(
        {
            "summary": '包含 "引號" 與中文',
            "details": {"next_step": "retrieve"},
            "later": "must not delay configured fields",
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )

    cursor = 0
    chunk_sizes = (1, 3, 2, 5, 4)
    saw_field_before_later = False
    index = 0
    while index < len(payload):
        chunk_size = chunk_sizes[cursor % len(chunk_sizes)]
        parser.feed(payload[index:index + chunk_size])
        cursor += 1
        index += chunk_size
        received = payload[:index]
        if emitted and '"later"' not in received:
            saw_field_before_later = True

    parser.feed("")

    assert emitted == [
        ("summary", '包含 "引號" 與中文'),
        ("details.next_step", "retrieve"),
    ]
    assert saw_field_before_later


def test_incremental_json_field_parser_and_final_response_accept_fenced_json() -> None:
    emitted: list[tuple[str, object]] = []
    parser = IncrementalJsonFieldParser(["summary"], lambda field, value: emitted.append((field, value)))

    parser.feed("```json\n{\"summary\":\"ready\"")
    parser.feed(",\"details\":{}}\n```")

    assert emitted == [("summary", "ready")]
    assert OpenAIChatResponse(
        content='```json\n{"summary":"ready","details":{}}\n```',
        model="test",
    ).as_json() == {"summary": "ready", "details": {}}


def test_incremental_json_field_parser_wildcard_emits_nested_values() -> None:
    emitted: list[tuple[str, object]] = []
    parser = IncrementalJsonFieldParser(["*"], lambda field, value: emitted.append((field, value)))

    parser.feed('{"intent":"question","details":{"source":{"kind":"memory"},"items":["a","b"]}}')

    assert {(field, json.dumps(value, ensure_ascii=False, sort_keys=True)) for field, value in emitted} == {
        ("intent", '"question"'),
        ("details.source.kind", '"memory"'),
        ("details.source", '{"kind": "memory"}'),
        ("details.items.0", '"a"'),
        ("details.items.1", '"b"'),
        ("details.items", '["a", "b"]'),
        ("details", '{"items": ["a", "b"], "source": {"kind": "memory"}}'),
    }


def test_events_schema_validates_and_normalizes_configuration() -> None:
    config = WorkflowConfig(
        events_schema={"action": {"label": "準備輸出回覆"}},
        modules={"action": ModuleSpec(kind="direct_answer")},
    )

    workflow = build_workflow(config)

    assert workflow.events_schema["action"]["label"] == "準備輸出回覆"
    assert workflow.events_schema == {
        "action": {"label": "準備輸出回覆", "fields": [], "metadata": {}}
    }

    with pytest.raises(ValueError, match="module key"):
        WorkflowConfig(events_schema={"unknown": {"label": "bad"}})
    with pytest.raises(TypeError, match="label"):
        WorkflowConfig(events_schema={"action": {"label": 1}})
    with pytest.raises(ValueError, match="dot path"):
        WorkflowConfig(events_schema={"perceive": {"label": "理解", "fields": ["details."]}})


def test_workflow_defaults_to_full_event_schema_and_emits_all_structured_fields() -> None:
    clients = [
        FoundryOpenAILikeClient(
            perceive_details={
                "next_step": "retrieve",
                "source": {"kind": "memory"},
            },
        ),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="最終回覆"),
        FoundryOpenAILikeClient(
            reflect_reason="looks good",
            reflect_suggestion="none",
        ),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            reflect=ResponseCheckReflect(**LLM_PARAMS),
        )

    events: list[dict[str, object]] = []
    result = workflow.run("請協助測試", event_callback=events.append)

    stage_events = [event for event in events if event["type"] == "stage"]
    field_events = [event for event in events if event["type"] == "structured_field"]
    token_events = [event for event in events if event["type"] == "token_delta"]

    assert result.final_message == "最終回覆"
    assert {module: schema["label"] for module, schema in workflow.events_schema.items()} == DEFAULT_LABELS
    assert {event["module"]: event["label"] for event in stage_events if event["phase"] == "start"} == DEFAULT_LABELS
    assert {event["phase"] for event in stage_events} == {"start", "finish"}
    assert {event["module"] for event in token_events} == {"perceive", "plan", "action", "reflect"}
    assert {(event["module"], event["field"]) for event in field_events} == {
        ("perceive", "intent"),
        ("perceive", "summary"),
        ("perceive", "details"),
        ("perceive", "details.next_step"),
        ("perceive", "details.source"),
        ("perceive", "details.source.kind"),
        ("plan", "thought"),
        ("plan", "next_module"),
        ("reflect", "verdict"),
        ("reflect", "reason"),
        ("reflect", "suggestion"),
    }
    fields_by_module: dict[str, dict[str, object]] = {}
    for event in field_events:
        fields_by_module.setdefault(str(event["module"]), {})[str(event["field"])] = event["value"]
    finish_fields_by_module = {
        event["module"]: event["fields"]
        for event in stage_events
        if event["phase"] == "finish"
    }
    assert finish_fields_by_module == {
        "perceive": [
            {"field": field, "value": value}
            for field, value in fields_by_module["perceive"].items()
        ],
        "plan": [
            {"field": field, "value": value}
            for field, value in fields_by_module["plan"].items()
        ],
        "retrieve": [],
        "action": [],
        "reflect": [
            {"field": field, "value": value}
            for field, value in fields_by_module["reflect"].items()
        ],
    }


def test_explicit_events_schema_restricts_stages_and_structured_fields() -> None:
    clients = [
        FoundryOpenAILikeClient(perceive_details={"next_step": "retrieve"}),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="最終回覆"),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            events_schema={"perceive": {"label": "自訂理解", "fields": ["summary"]}},
        )

    events: list[dict[str, object]] = []
    workflow.run("請協助測試", event_callback=events.append)

    assert {event["module"] for event in events if event["type"] == "stage"} == {"perceive"}
    assert {(event["module"], event["field"]) for event in events if event["type"] == "structured_field"} == {
        ("perceive", "summary"),
    }
    assert {event["module"] for event in events if event["type"] == "token_delta"} == {"perceive"}
    assert next(
        event["fields"]
        for event in events
        if event["type"] == "stage" and event["module"] == "perceive" and event["phase"] == "finish"
    ) == [
        {"field": event["field"], "value": event["value"]}
        for event in events
        if event["type"] == "structured_field" and event["module"] == "perceive"
    ]


def test_default_schema_emits_an_abort_stage_event() -> None:
    workflow = Workflow(gates=Gates(max_node_hops=0))
    events: list[dict[str, object]] = []

    result = workflow.run("請協助測試", event_callback=events.append)

    assert result.aborted is True
    assert [
        (event["module"], event["phase"], event["label"])
        for event in events
        if event["type"] == "stage"
    ] == [("perceive", "abort", DEFAULT_LABELS["perceive"])]


def test_workflow_stream_uses_the_same_default_event_schema() -> None:
    clients = [
        FoundryOpenAILikeClient(perceive_details={"next_step": "retrieve"}),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="串流回覆"),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
        )

    events: list[dict[str, object]] = []
    stream = workflow.stream("測試串流", event_callback=events.append, yield_action_deltas=True)

    assert "".join(stream) == "串流回覆"
    assert stream.result.final_message == "串流回覆"
    assert {event["module"]: event["label"] for event in events if event["type"] == "stage" and event["phase"] == "start"} == {
        module: DEFAULT_LABELS[module]
        for module in ("perceive", "plan", "retrieve", "action")
    }
    assert {(event["module"], event["field"]) for event in events if event["type"] == "structured_field"} == {
        ("perceive", "intent"),
        ("perceive", "summary"),
        ("perceive", "details"),
        ("perceive", "details.next_step"),
        ("plan", "thought"),
        ("plan", "next_module"),
    }


def test_workflow_run_emits_configured_structured_fields_with_event_identity() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="最終回覆"),
        FoundryOpenAILikeClient(reflect_reason="looks good"),
    ]
    schema = {
        **EVENTS_SCHEMA,
        "reflect": {"label": "檢查回覆", "fields": ["reason"]},
    }
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            reflect=ResponseCheckReflect(**LLM_PARAMS),
            events_schema=schema,
        )

    events: list[dict[str, object]] = []
    result = workflow.run(
        "請協助測試",
        workflow_id="workflow-1",
        session_id="session-1",
        event_callback=events.append,
    )
    field_events = [event for event in events if event["type"] == "structured_field"]

    assert result.final_message == "最終回覆"
    assert {(event["module"], event["field"]) for event in field_events} == {
        ("perceive", "summary"),
        ("plan", "thought"),
        ("plan", "next_module"),
        ("reflect", "reason"),
    }
    assert len(field_events) == 4
    assert all(event["phase"] == "field" and event["status"] == "completed" for event in field_events)
    assert all(event["workflow_id"] == "workflow-1" for event in field_events)
    assert all(event["session_id"] == "session-1" for event in field_events)
    assert all(str(event["visit_id"]).startswith("workflow-1:") for event in field_events)
    assert next(
        event for event in events if event["type"] == "stage" and event["module"] == "action"
    )["label"] == "準備輸出回覆"
    assert next(event for event in field_events if event["field"] == "summary")["schema"] == {
        "label": "理解輸入",
        "fields": ["summary", "details.next_step"],
        "metadata": {},
    }


def test_workflow_stream_forwards_structured_events_without_yielding_them() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="串流回覆"),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            events_schema=EVENTS_SCHEMA,
        )

    events: list[dict[str, object]] = []
    stream = workflow.stream(
        "測試串流欄位",
        event_callback=events.append,
        yield_action_deltas=True,
    )

    assert "".join(stream) == "串流回覆"
    assert stream.result.final_message == "串流回覆"
    assert any(event["type"] == "structured_field" and event["field"] == "summary" for event in events)
    assert all(
        event.get("module") == "action"
        for event in events
        if event["type"] == "token_delta" and event["metadata"].get("structured") is False
    )
