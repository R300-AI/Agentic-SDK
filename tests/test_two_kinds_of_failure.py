"""An endpoint that will not answer is not the same as a model that answered badly.

Observed through ``Workflow.run()``: one of them is worth asking planning about,
the other is worth stopping for. Retrying a planning decision against an
endpoint that is down just spends the same call again.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_sdk import (
    DirectAnswerAction,
    PassThroughPerceive,
    NextStepPlan,
    PassThroughPlan,
    PassThroughRetrieve,
    TextPerceive,
    Workflow,
)

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


def _workflow_whose_perception_uses_a_model():
    perceive_client = FoundryOpenAILikeClient()
    plan_client = FoundryOpenAILikeClient(plan_sequence=["action"])
    with patch(
        "agentic_sdk.llm.openai_compatible.OpenAI",
        side_effect=[perceive_client, plan_client],
    ):
        workflow = Workflow(
            perceive=TextPerceive(**LLM_PARAMS),
            plan=PassThroughPlan(),
            retrieve=PassThroughRetrieve(),
            action=DirectAnswerAction(),
        )
    return workflow, perceive_client


def test_an_endpoint_that_will_not_answer_stops_the_run():
    workflow, perceive_client = _workflow_whose_perception_uses_a_model()

    def refuse(**_kwargs):
        raise ConnectionError("connection refused")

    perceive_client.chat.completions.create = refuse

    result = workflow.run("保固多久？")

    assert result.stop_reason == "endpoint_unavailable", (
        "asking planning what to do about an endpoint that is down spends the same call again"
    )
    assert result.visit_counts.get("plan", 0) == 0, "planning is not asked"


class _CannotUseWhatItGot:
    """A module that got an answer and could not make sense of it."""

    name = "retrieve"

    def __call__(self, state):
        raise ValueError("could not make sense of what came back")


def test_a_module_that_could_not_use_what_it_got_is_handed_to_planning():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=_CannotUseWhatItGot(),
        action=DirectAnswerAction(),
    ).run("保固多久？")

    assert result.stop_reason == "end_turn", "one step not working out is not the run failing"
    assert result.visit_counts.get("plan", 0) >= 1, "planning decides what to do about it"


def test_the_two_are_told_apart_by_the_result_alone():
    workflow, client = _workflow_whose_perception_uses_a_model()

    def refuse(**_kwargs):
        raise ConnectionError("refused")

    client.chat.completions.create = refuse
    endpoint_down = workflow.run("保固多久？")

    could_not_use_it = Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=_CannotUseWhatItGot(),
        action=DirectAnswerAction(),
    ).run("保固多久？")

    assert endpoint_down.stop_reason != could_not_use_it.stop_reason, (
        "a caller must be able to tell which happened from the result alone"
    )
    assert endpoint_down.visit_counts.get("plan", 0) < could_not_use_it.visit_counts.get("plan", 0)


def test_an_endpoint_failure_hands_over_what_was_already_delivered():
    workflow, perceive_client = _workflow_whose_perception_uses_a_model()

    def refuse(**_kwargs):
        raise ConnectionError("connection refused")

    perceive_client.chat.completions.create = refuse

    result = workflow.run("保固多久？")

    assert "connection refused" not in result.final_message, (
        "the endpoint's own wording is for the trace, not for the person"
    )


def test_the_inference_layer_keeps_its_own_retry_count():
    from agentic_sdk.llm.openai_compatible import resolve_openai_client

    with patch("agentic_sdk.llm.openai_compatible.OpenAI") as made:
        resolve_openai_client("x", api_key="k", base_url="https://example.test/v1")

    assert "max_retries" not in made.call_args.kwargs, (
        "the SDK's own default is what this layer uses; overriding it here would hide it"
    )


def test_endpoint_unavailable_is_one_of_the_named_stop_reasons():
    from agentic_sdk.core.module import STOPPED_ITSELF

    assert "endpoint_unavailable" in STOPPED_ITSELF
