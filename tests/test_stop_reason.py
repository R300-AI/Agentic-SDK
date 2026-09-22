"""Why a run stopped, in one field.

Observed through ``Workflow.run()``: build a workflow that stops in a
particular way, run it, and read the result. A caller should not have to
cross-reference several booleans to say what happened.
"""

from __future__ import annotations

import time

import pytest

from agentic_sdk import (
    DirectAnswerAction,
    Gates,
    PassThroughPerceive,
    PassThroughPlan,
    PassThroughRetrieve,
    Workflow,
)
from agentic_sdk.core.cancellation import CancellationToken


def _workflow(**kwargs) -> Workflow:
    return Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        **kwargs,
    )


class _Boom:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, state):
        raise RuntimeError(f"{self.name} blew up")


class _GoesRoundForever:
    name = "plan"

    def __call__(self, state):
        return {"next_module": "retrieve", "payload": {}, "context_updates": []}


def test_a_run_that_finished_says_so(tmp_path=None):
    result = _workflow().run("保固多久？")

    assert result.stop_reason == "end_turn", "every run says why it stopped, including the ordinary way"


def test_being_interrupted_is_not_a_fault():
    cancel = CancellationToken()
    cancel.cancel("someone spoke")

    result = _workflow().run("保固多久？", cancel=cancel)

    assert result.stop_reason == "interrupted"


def test_going_round_too_many_times_says_which_limit():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_GoesRoundForever(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        gates=Gates(max_node_hops=6),
    ).run("保固多久？")

    assert result.stop_reason == "max_hops", "a run going round is not the same fault as a slow endpoint"


def test_one_module_visited_too_often_says_which_limit():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_GoesRoundForever(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        gates=Gates(max_node_hops=100, max_revisit=3),
    ).run("保固多久？")

    assert result.stop_reason == "max_revisit"


def test_taking_too_long_says_so():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_GoesRoundForever(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        gates=Gates(max_node_hops=10_000, max_revisit=10_000, timeout_sec=0.0),
    ).run("保固多久？")

    assert result.stop_reason == "timeout"


def test_planning_failing_says_that_rather_than_a_limit():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_Boom("plan"),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
    ).run("保固多久？")

    assert result.stop_reason == "planning_failed", "nothing else decides, which is not a limit being hit"


def test_a_workflow_pointed_at_a_module_that_is_not_there_says_it_is_misconfigured():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_GoesRoundForever(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        entry_module="nowhere",
    ).run("保固多久？")

    assert result.stop_reason == "misconfigured", "a setup mistake reads differently from a limit"


def test_the_three_flags_are_gone():
    result = _workflow().run("保固多久？")

    for gone in ("aborted", "abort_reason", "interrupted"):
        assert not hasattr(result, gone), f"{gone} said part of what stop_reason now says in full"


def test_how_much_was_delivered_is_still_reported():
    cancel = CancellationToken()
    cancel.cancel("someone spoke", delivered="說到一半")

    result = _workflow().run("保固多久？", cancel=cancel)

    assert result.interrupt_payload, "that field carries how much landed, which is not why it stopped"


def test_hitting_a_limit_hands_over_what_was_produced_rather_than_an_error_banner():
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=_GoesRoundForever(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        gates=Gates(max_node_hops=6),
    ).run("保固多久？")

    assert "exceeded" not in result.final_message, "the limit's wording is for the trace, not for the person"


@pytest.mark.parametrize(
    "reason",
    ["end_turn", "interrupted", "max_hops", "max_revisit", "timeout", "budget_exhausted", "planning_failed", "misconfigured"],
)
def test_every_stop_reason_is_a_named_one(reason):
    from agentic_sdk.core.module import STOP_REASONS

    assert reason in STOP_REASONS, "the set is closed, so a caller can switch on it exhaustively"
