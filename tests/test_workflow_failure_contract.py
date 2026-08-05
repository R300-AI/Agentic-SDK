from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_sdk import GenerativeAction, NextStepPlan, PassThroughRetrieve, TextPerceive, Workflow
from agentic_sdk.core import ContextEntryType

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


def _raise_connection_error(**_kwargs):
    raise RuntimeError("provider connection unavailable")


@pytest.mark.parametrize(
    "failed_stage,expected_message",
    [
        ("perceive", "Unable to understand the input right now."),
        ("plan", "Unable to plan the next step right now."),
    ],
)
def test_provider_failure_in_non_action_stage_returns_controlled_aborted_result(failed_stage, expected_message):
    perceive_client = FoundryOpenAILikeClient()
    plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve"])
    action_client = FoundryOpenAILikeClient(action_text="not reached")
    with patch(
        "agentic_sdk.llm.openai_compatible.OpenAI",
        side_effect=[perceive_client, plan_client, action_client],
    ):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
        )

    failed_client = perceive_client if failed_stage == "perceive" else plan_client
    failed_client.chat.completions.create = _raise_connection_error

    result = workflow.run("測試 provider failure")

    assert result.aborted is True
    assert result.abort_reason == expected_message
    assert result.final_message == f"[workflow ended with error] {expected_message}"
    assert result.entries[-1].metadata == {"ok": False, "stage": failed_stage, "error_type": "RuntimeError"}
    assert result.entries[-1].type == (
        ContextEntryType.PERCEIVED if failed_stage == "perceive" else ContextEntryType.PLAN_DECISION
    )
    assert "provider connection unavailable" not in result.final_message
