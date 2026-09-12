"""The planning module takes up a skill — ADR-0006.

Observed through ``Workflow.run()``: what the planning module was shown, what
the action module received, and what the conversation holds afterwards.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_sdk import Workflow
from agentic_sdk.modules import GenerativeAction, NextStepWithSkills, PassThroughPerceive, PassThroughRetrieve

from support import FoundryOpenAILikeClient, write_skill_package


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}

WRITE_BODY = "寫作技能：先確認章節目標。"
REVIEW_BODY = "審稿技能：逐段標出問題。"
SUBMIT_BODY = "送件技能：先確認收件人。"


def _package(root):
    return write_skill_package(
        root,
        skills={
            "write": {"description": "把計畫書的一章寫出來", "body": WRITE_BODY},
            "review": {"description": "審一份已經寫好的稿", "body": REVIEW_BODY},
            "submit": {"description": "送出申請並通知窗口", "body": SUBMIT_BODY, "withheld_from_planning": True},
        },
    )


def _request_text(client: FoundryOpenAILikeClient) -> str:
    return "\n".join(str(message["content"]) for message in client.last_create_kwargs["messages"])


def _agent(package, *, plan_skill: str | None = ""):
    plan_client = FoundryOpenAILikeClient(plan_sequence=["action"], plan_skill=plan_skill)
    action_client = FoundryOpenAILikeClient(action_text="好的。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=[plan_client, action_client]):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepWithSkills(skill_packages=[package], **LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
        )
    return workflow, plan_client, action_client


def _skill_turns(result):
    return [turn for turn in result.memory.turns if (turn.metadata or {}).get("skill")]


def test_the_planning_module_is_shown_every_skill_it_may_pick(tmp_path) -> None:
    workflow, plan_client, _ = _agent(_package(tmp_path))

    workflow.run("幫我處理這份計畫書")

    heard = _request_text(plan_client)
    assert "write" in heard and "把計畫書的一章寫出來" in heard
    assert "review" in heard and "審一份已經寫好的稿" in heard
    # Withheld from its own choosing, so it is not offered.
    assert "送出申請並通知窗口" not in heard


def test_a_skill_the_planning_module_picks_reaches_the_action_module(tmp_path) -> None:
    workflow, _, action_client = _agent(_package(tmp_path), plan_skill="write")

    result = workflow.run("寫第三章")

    assert WRITE_BODY in _request_text(action_client)
    assert [turn.metadata["skill"] for turn in _skill_turns(result)] == ["write"]


def test_the_skill_joins_the_conversation_without_touching_what_was_said(tmp_path) -> None:
    workflow, _, _ = _agent(_package(tmp_path), plan_skill="write")

    result = workflow.run("寫第三章")

    said = [turn for turn in result.memory.turns if turn.role == "user" and not (turn.metadata or {}).get("skill")]
    assert [turn.content for turn in said] == ["寫第三章"]
    taken_up = _skill_turns(result)[0]
    assert taken_up.role == "user"
    assert WRITE_BODY in taken_up.content


def test_the_person_naming_a_skill_overrules_the_planning_module(tmp_path) -> None:
    workflow, _, action_client = _agent(_package(tmp_path), plan_skill="write")

    result = workflow.run("/review 幫我看看這一章")

    assert REVIEW_BODY in _request_text(action_client)
    assert WRITE_BODY not in _request_text(action_client)
    assert [turn.metadata["skill"] for turn in _skill_turns(result)] == ["review"]


def test_a_skill_withheld_from_the_planning_module_still_answers_to_its_name(tmp_path) -> None:
    workflow, _, action_client = _agent(_package(tmp_path), plan_skill="")

    result = workflow.run("/submit 幫我送出")

    assert SUBMIT_BODY in _request_text(action_client)
    assert [turn.metadata["skill"] for turn in _skill_turns(result)] == ["submit"]


def test_a_name_that_is_not_mounted_is_ordinary_text(tmp_path) -> None:
    workflow, _, action_client = _agent(_package(tmp_path), plan_skill="")

    result = workflow.run("/usr/local/bin 這個路徑是什麼？")

    assert _skill_turns(result) == []
    assert "/usr/local/bin" in _request_text(action_client)


def test_a_name_the_model_invents_is_ignored(tmp_path) -> None:
    workflow, _, _ = _agent(_package(tmp_path), plan_skill="translate")

    result = workflow.run("幫我翻譯這一段")

    assert _skill_turns(result) == []


@pytest.mark.parametrize("memory_type", ["in_context", "persistent"])
def test_a_skill_taken_up_stays_for_the_rest_of_the_conversation(tmp_path, memory_type) -> None:
    plan_client = FoundryOpenAILikeClient(plan_sequence=["action"], plan_skill="write")
    action_client = FoundryOpenAILikeClient(action_text="好的。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=[plan_client, action_client]):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepWithSkills(skill_packages=[_package(tmp_path)], **LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            memory_type=memory_type,
        )

    workflow.run("寫第三章", session_id="s1")
    plan_client.plan_skill = ""
    result = workflow.run("改短一點", session_id="s1")

    heard = _request_text(action_client)
    assert WRITE_BODY in heard and "改短一點" in heard
    # Taken up once; the conversation carries it, nothing re-reads the package.
    assert [turn.metadata["skill"] for turn in _skill_turns(result)] == ["write"]


def test_a_conversation_can_take_up_a_second_skill(tmp_path) -> None:
    plan_client = FoundryOpenAILikeClient(plan_sequence=["action"], plan_skill="write")
    action_client = FoundryOpenAILikeClient(action_text="好的。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=[plan_client, action_client]):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepWithSkills(skill_packages=[_package(tmp_path)], **LLM_PARAMS),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
        )

    workflow.run("寫第三章", session_id="s1")
    result = workflow.run("/review 換成審稿", session_id="s1")

    assert [turn.metadata["skill"] for turn in _skill_turns(result)] == ["write", "review"]
    heard = _request_text(action_client)
    assert WRITE_BODY in heard and REVIEW_BODY in heard


def test_the_trace_says_which_skill_this_turn_took_up(tmp_path) -> None:
    workflow, _, _ = _agent(_package(tmp_path), plan_skill="write")
    events: list[dict] = []

    result = workflow.run("寫第三章", event_callback=events.append)

    decision = [entry for entry in result.entries if entry.type.value == "plan_decision"][-1]
    assert decision.metadata["skill"] == "write"
    assert result.entities["picked_skill"] == "write"
    finish = next(event for event in events if event.get("type") == "stage" and event["phase"] == "finish" and event["stage"] == "plan")
    assert finish["output"]["payload"]["picked_skill"] == "write"


def test_the_workflow_itself_knows_nothing_about_skills(tmp_path) -> None:
    with pytest.raises(TypeError):
        Workflow(perceive=PassThroughPerceive(), skill_packages=[_package(tmp_path)])
    workflow, _, _ = _agent(_package(tmp_path))
    with pytest.raises(TypeError):
        workflow.run("寫第三章", skill="write")
