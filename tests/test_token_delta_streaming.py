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
