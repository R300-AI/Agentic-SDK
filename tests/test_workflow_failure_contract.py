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


def _workflow_whose_provider_fails(failed_stage: str):
    perceive_client = FoundryOpenAILikeClient()
    plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "reflect", "action"])
    action_client = FoundryOpenAILikeClient(action_text="answered anyway")
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
    return workflow


def test_a_provider_failure_before_planning_is_handed_to_planning():
    result = _workflow_whose_provider_fails("perceive").run("測試 provider failure")

    assert result.aborted is False, "the endpoint wobbled; the run did not fail"
    failure = next(entry for entry in result.entries if entry.is_error)
    assert failure.type == ContextEntryType.PERCEIVED
    assert failure.content == "Unable to understand the input right now."
    assert failure.metadata["stage"] == "perceive"
    assert failure.metadata["error_type"] == "RuntimeError"
    assert "provider connection unavailable" not in result.final_message


def test_planning_own_provider_failure_ends_the_run_with_a_plain_message():
    result = _workflow_whose_provider_fails("plan").run("測試 provider failure")

    assert result.aborted is True, "nothing else decides what to do next"
    assert result.abort_reason == "Unable to plan the next step right now."
    assert result.final_message == "[workflow ended with error] Unable to plan the next step right now."
    assert "provider connection unavailable" not in result.final_message


class _Boom:
    """A module that fails the way a third-party one does: by raising."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, state):
        raise RuntimeError(f"{self.name} blew up")


def _workflow_with_failing(failing: str) -> Workflow:
    from agentic_sdk import DirectAnswerAction, EvidenceCheckReflect, PassThroughPerceive, PassThroughPlan

    modules = {
        "perceive": PassThroughPerceive(),
        "plan": PassThroughPlan(),
        "retrieve": PassThroughRetrieve(),
        "action": DirectAnswerAction(),
        "reflect": EvidenceCheckReflect(),
    }
    modules[failing] = _Boom(failing)
    return Workflow(
        perceive=modules["perceive"],
        plan=modules["plan"],
        retrieve=modules["retrieve"],
        action=modules["action"],
        reflect=modules["reflect"],
    )


ENTRY_TYPE_FOR = {
    "perceive": ContextEntryType.PERCEIVED,
    "retrieve": ContextEntryType.RETRIEVED,
    "action": ContextEntryType.ACTION_RESULT,
    "reflect": ContextEntryType.REFLECTION,
}


@pytest.mark.parametrize("failing", ["perceive", "retrieve", "reflect", "action"])
def test_a_raising_module_does_not_abort_the_run(failing):
    result = _workflow_with_failing(failing).run("保固多久？")

    assert result.aborted is False, "one module failing is not the workflow protecting itself"


@pytest.mark.parametrize("failing", ["perceive", "retrieve", "reflect"])
def test_planning_is_asked_what_to_do_about_a_failure(failing):
    result = _workflow_with_failing(failing).run("保固多久？")

    assert result.visit_counts.get("plan", 0) >= 1


def test_an_answer_that_could_not_be_produced_still_says_so():
    result = _workflow_with_failing("action").run("保固多久？")

    assert result.visit_counts["action"] == 1, "the action ends the run either way — ADR-0005"
    assert "Unable to produce an answer right now." in result.final_message
    assert "blew up" not in result.final_message


@pytest.mark.parametrize("failing", ["perceive", "retrieve", "action", "reflect"])
def test_the_failure_is_recorded_under_that_module_own_entry_type(failing):
    result = _workflow_with_failing(failing).run("保固多久？")

    failures = [entry for entry in result.entries if entry.is_error]
    assert len(failures) >= 1, "the failure is on the context, not dropped"
    assert failures[0].type == ENTRY_TYPE_FOR[failing]


@pytest.mark.parametrize("failing", ["perceive", "retrieve", "action", "reflect"])
def test_the_recorded_failure_says_what_happened_without_leaking_the_exception(failing):
    result = _workflow_with_failing(failing).run("保固多久？")

    failure = next(entry for entry in result.entries if entry.is_error)
    assert "blew up" not in failure.content, "the person reading this is not the developer"
    assert failure.metadata.get("error_type") == "RuntimeError"
    assert "blew up" in str(failure.metadata.get("error_message", "")), "the developer still needs the original"


def test_planning_failing_ends_the_run_rather_than_looping_back_to_itself():
    result = _workflow_with_failing("plan").run("保固多久？")

    assert result.visit_counts.get("plan", 0) == 1, "nothing else decides, so it does not go round again"


def test_a_failure_is_announced_on_the_event_stream():
    events: list[dict] = []
    _workflow_with_failing("retrieve").run("保固多久？", event_callback=events.append)

    failed = [event for event in events if event.get("status") == "error" and event.get("module") == "retrieve"]
    assert failed, "whoever is watching the trace needs to see which module failed"


def test_what_is_remembered_never_carries_the_exception():
    from agentic_sdk import InMemoryStore

    store = InMemoryStore()
    result = _workflow_with_failing("retrieve").run("保固多久？", memory=store)

    remembered = " ".join(str(turn.content) for turn in store.turns)
    assert remembered, "the run did deliver something, so there is something to check"
    assert "blew up" not in remembered and "RuntimeError" not in remembered
    assert "blew up" not in result.final_message
