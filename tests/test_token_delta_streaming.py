from __future__ import annotations

from unittest.mock import patch

from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, NextStepPlan, PassThroughRetrieve, TextPerceive
from agentic_sdk.modules.reflect import ResponseCheckReflect
from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


def test_workflow_emits_structured_and_action_token_deltas() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="這是最終回覆。"),
        FoundryOpenAILikeClient(),
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
    result = workflow.run("請協助測試串流", event_callback=events.append)

    token_events = [event for event in events if event["type"] == "token_delta"]
    assert result.final_message == "這是最終回覆。"
    assert {event["module"] for event in token_events} == {"perceive", "plan", "action", "reflect"}
    assert all(event["content"] for event in token_events)
    assert all(event["phase"] == "delta" and event["status"] == "streaming" for event in token_events)
    assert all(event["metadata"]["structured"] is True for event in token_events if event["module"] != "action")
    assert all(event["metadata"]["structured"] is False for event in token_events if event["module"] == "action")
    assert "".join(event["content"] for event in token_events if event["module"] == "action") == result.final_message


def test_tool_call_action_keeps_streamed_tool_calls() -> None:
    tool_calls = [
        {
            "id": "call_booking",
            "type": "function",
            "function": {"name": "submit_booking", "arguments": '{"date":"明天"}'},
        }
    ]
    client = FoundryOpenAILikeClient(action_text="請選擇日期。", tool_calls=tool_calls)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        from agentic_sdk.modules import ToolCallAction

        workflow = Workflow(
            retrieve=PassThroughRetrieve(),
            action=ToolCallAction(
                **LLM_PARAMS,
                tools=[{"type": "function", "function": {"name": "submit_booking"}}],
            ),
        )

    events: list[dict[str, object]] = []
    result = workflow.run("我要訂位", event_callback=events.append)

    assert result.final_message == "請選擇日期。"
    assert result.entities["latest_tool_calls"] == tool_calls
    assert client.last_create_kwargs["stream"] is True
    assert "".join(event["content"] for event in events if event["type"] == "token_delta") == result.final_message


def test_workflow_stream_forwards_events_while_yielding_only_action_text() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="串流 Action 回覆。"),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            events_schema={
                "perceive": {"label": "perceive"},
                "plan": {"label": "plan"},
                "retrieve": {"label": "retrieve"},
                "action": {"label": "action"},
            },
        )

    events: list[dict[str, object]] = []
    stream = workflow.stream("測試完整事件", event_callback=events.append)
    assert "".join(stream) == ""
    assert stream.result.final_message == "串流 Action 回覆。"
    assert {event["module"] for event in events if event["type"] == "token_delta"} == {"perceive", "plan", "action"}
    assert [event["phase"] for event in events if event["type"] == "stage"] == [
        "start",
        "finish",
        "start",
        "finish",
        "start",
        "finish",
        "start",
        "finish",
    ]


def test_workflow_stream_can_explicitly_yield_action_deltas_with_event_callback() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="雙通道回覆。"),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
        )

    events: list[dict[str, object]] = []
    stream = workflow.stream(
        "測試雙通道",
        event_callback=events.append,
        yield_action_deltas=True,
    )
    assert "".join(stream) == "雙通道回覆。"
    assert stream.result.final_message == "雙通道回覆。"
    assert "".join(
        event["content"]
        for event in events
        if event["type"] == "token_delta" and event["module"] == "action"
    ) == "雙通道回覆。"


def test_workflow_stream_yields_only_action_text_and_exposes_final_result() -> None:
    clients = [
        FoundryOpenAILikeClient(),
        FoundryOpenAILikeClient(plan_sequence=["retrieve"]),
        FoundryOpenAILikeClient(action_text="這是直接串流回覆。"),
        FoundryOpenAILikeClient(),
    ]
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=clients):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            reflect=ResponseCheckReflect(**LLM_PARAMS),
        )

    stream = workflow.stream("請協助測試直接串流")

    deltas = list(stream)

    assert "".join(deltas) == "這是直接串流回覆。"
    assert all(not delta.startswith("{") for delta in deltas)
    assert stream.result.final_message == "這是直接串流回覆。"
    assert stream.result.visit_counts == {"perceive": 1, "plan": 1, "retrieve": 1, "action": 1, "reflect": 1}


def test_workflow_stream_result_requires_completed_iteration() -> None:
    client = FoundryOpenAILikeClient(action_text="完成後才可取得結果。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(retrieve=PassThroughRetrieve(), action=GenerativeAction(**LLM_PARAMS))

    stream = workflow.stream("測試結果")

    try:
        _ = stream.result
    except RuntimeError as exc:
        assert "after the stream is exhausted" in str(exc)
    else:
        raise AssertionError("result should require completed iteration")

    assert "".join(stream) == "完成後才可取得結果。"
    assert stream.result.final_message == "完成後才可取得結果。"


def test_workflow_stream_preserves_tool_call_result() -> None:
    tool_calls = [
        {
            "id": "call_booking",
            "type": "function",
            "function": {"name": "submit_booking", "arguments": '{"date":"明天"}'},
        }
    ]
    client = FoundryOpenAILikeClient(action_text="請選擇日期。", tool_calls=tool_calls)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        from agentic_sdk.modules import ToolCallAction

        workflow = Workflow(
            retrieve=PassThroughRetrieve(),
            action=ToolCallAction(
                **LLM_PARAMS,
                tools=[{"type": "function", "function": {"name": "submit_booking"}}],
            ),
        )

    stream = workflow.stream("我要訂位")

    assert "".join(stream) == "請選擇日期。"
    assert stream.result.entities["latest_tool_calls"] == tool_calls


def test_workflow_stream_preserves_action_error_result() -> None:
    client = FoundryOpenAILikeClient()
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(retrieve=PassThroughRetrieve(), action=GenerativeAction(**LLM_PARAMS))

    def raise_connection_error(**kwargs):
        raise RuntimeError("connection unavailable")

    client.chat.completions.create = raise_connection_error
    stream = workflow.stream("測試 action error")

    assert list(stream) == ["[workflow ended with error] connection unavailable"]
    assert stream.result.final_message == "[workflow ended with error] connection unavailable"
    assert stream.result.aborted is False
