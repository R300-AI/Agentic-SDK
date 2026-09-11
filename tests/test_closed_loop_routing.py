"""Every run closes the loop through planning — ADR-0005.

Observed through ``Workflow.run()`` only: the order of stage events, the visit
counts and the entries a run leaves behind.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_sdk import Gates, GateConfig, ModuleSpec, Workflow, WorkflowConfig, build_workflow
from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput
from agentic_sdk.modules import (
    DirectAnswerAction,
    EvidenceCheckReflect,
    GenerativeAction,
    KeywordRetrieve,
    NextStepPlan,
    PassThroughPerceive,
    PassThroughRetrieve,
)

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}

ITEMS = [{"keywords": ["保固"], "content": "本產品保固十二個月。"}]


def _refuse(**_kwargs):
    raise RuntimeError("provider down")


def _stages(events: list[dict]) -> list[str]:
    return [event["stage"] for event in events if event.get("type") == "stage" and event["phase"] == "start"]


def _finish(events: list[dict], stage: str) -> list[dict]:
    return [event for event in events if event.get("type") == "stage" and event["phase"] == "finish" and event["stage"] == stage]


class ScriptedPlan:
    """Chooses the next step from a fixed list, and remembers what it was offered."""

    name = "plan"

    def __init__(self, choices: list[object]) -> None:
        self._choices = list(choices)
        self.offered: list[list[str]] = []

    def __call__(self, state):
        self.offered.append(list(state.plan_options))
        choice = self._choices.pop(0) if self._choices else "action"
        return ModuleOutput(next_module=choice)


class RecordingReflect:
    name = "reflect"

    def __call__(self, state):
        return ModuleOutput(
            next_module=None,
            context_updates=[ContextEntry(type=ContextEntryType.REFLECTION, content="checked", metadata={"verdict": "pass"})],
        )


def test_a_workflow_without_a_planning_module_plans_by_a_fixed_rule():
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
    )
    events: list[dict] = []

    result = workflow.run("保固多久？", event_callback=events.append)

    assert result.final_message == "本產品保固十二個月。"
    assert _stages(events) == ["perceive", "plan", "retrieve", "plan", "action"]
    assert result.visit_counts == {"perceive": 1, "plan": 2, "retrieve": 1, "action": 1}


def test_perception_and_retrieval_say_they_hand_over_to_planning():
    workflow = Workflow(perceive=PassThroughPerceive(), retrieve=KeywordRetrieve(items=ITEMS), action=DirectAnswerAction())
    events: list[dict] = []

    workflow.run("保固多久？", event_callback=events.append)

    assert _finish(events, "perceive")[0]["output"]["next_module"] == "plan"
    assert _finish(events, "retrieve")[0]["output"]["next_module"] == "plan"


def test_the_fixed_rule_sends_the_lookup_to_reflect_once_before_acting():
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
    )
    events: list[dict] = []

    result = workflow.run("保固多久？", event_callback=events.append)

    assert _stages(events) == ["perceive", "plan", "retrieve", "plan", "reflect", "plan", "action"]
    assert result.visit_counts == {"perceive": 1, "plan": 3, "retrieve": 1, "reflect": 1, "action": 1}
    types = [entry.type for entry in result.entries]
    assert types.index(ContextEntryType.REFLECTION) < types.index(ContextEntryType.ACTION_RESULT)


def test_the_route_ignores_where_other_modules_say_to_go():
    class StraightToAction(KeywordRetrieve):
        def __call__(self, state):
            return {**super().__call__(state), "next_module": "action"}

    class BackToReflect(DirectAnswerAction):
        def __call__(self, state):
            return {**super().__call__(state), "next_module": "reflect"}

    workflow = Workflow(
        perceive=PassThroughPerceive(),
        retrieve=StraightToAction(items=ITEMS),
        action=BackToReflect(),
        reflect=RecordingReflect(),
    )
    events: list[dict] = []

    workflow.run("保固多久？", event_callback=events.append)

    assert _stages(events) == ["perceive", "plan", "retrieve", "plan", "reflect", "plan", "action"]


def test_a_failed_action_ends_the_run_without_a_check_after_it():
    client = FoundryOpenAILikeClient()
    client.chat.completions.create = _refuse
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=GenerativeAction(**LLM_PARAMS),
            reflect=RecordingReflect(),
        )
    events: list[dict] = []

    result = workflow.run("保固多久？", event_callback=events.append)

    assert _stages(events)[-1] == "action"
    assert result.visit_counts["reflect"] == 1
    assert result.final_message.startswith("[workflow ended with error]")
    assert result.aborted is False


@pytest.mark.parametrize("choice", ["perceive", None, "somewhere", "reflect"])
def test_a_choice_planning_cannot_make_becomes_action(choice):
    plan = ScriptedPlan([choice])
    workflow = Workflow(perceive=PassThroughPerceive(), plan=plan, retrieve=KeywordRetrieve(items=ITEMS), action=DirectAnswerAction())
    events: list[dict] = []

    result = workflow.run("保固多久？", event_callback=events.append)

    assert _stages(events) == ["perceive", "plan", "action"]
    assert _finish(events, "plan")[0]["next_module"] == "action"
    assert result.aborted is False


def test_planning_is_offered_reflect_only_when_a_reflect_module_is_mounted():
    without = ScriptedPlan(["action"])
    Workflow(perceive=PassThroughPerceive(), plan=without, retrieve=KeywordRetrieve(items=ITEMS), action=DirectAnswerAction()).run("保固多久？")
    with_reflect = ScriptedPlan(["action"])
    Workflow(
        perceive=PassThroughPerceive(),
        plan=with_reflect,
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
    ).run("保固多久？")

    assert without.offered == [["retrieve", "action"]]
    assert with_reflect.offered == [["retrieve", "reflect", "action"]]


def test_planning_is_not_held_to_the_revisit_limit():
    plan = ScriptedPlan(["retrieve", "retrieve", "reflect", "action"])
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        plan=plan,
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
        gates=Gates(max_revisit=2),
    )

    result = workflow.run("保固多久？")

    assert result.aborted is False
    assert result.visit_counts["plan"] == 4


def test_other_steps_are_still_held_to_the_revisit_limit():
    plan = ScriptedPlan(["retrieve", "retrieve", "retrieve", "action"])
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        plan=plan,
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        gates=Gates(max_revisit=2),
    )

    result = workflow.run("保固多久？")

    assert result.aborted is True
    assert result.abort_reason == "module 'retrieve' exceeded revisit limit 2"


def test_next_step_plan_can_send_the_lookup_to_reflect():
    client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "reflect", "action"])
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=EvidenceCheckReflect(),
        )
    events: list[dict] = []

    result = workflow.run("保固多久？", event_callback=events.append)

    assert _stages(events) == ["perceive", "plan", "retrieve", "plan", "reflect", "plan", "action"]
    assert result.final_message == "本產品保固十二個月。"


def test_pass_through_plan_is_a_canonical_module():
    from agentic_sdk import PassThroughPlan
    from agentic_sdk.modules import PassThroughPlan as FromModules

    workflow = build_workflow(
        WorkflowConfig(
            modules={
                "plan": ModuleSpec(kind="pass_through_plan"),
                "retrieve": ModuleSpec(kind="keyword", params={"items": ITEMS}),
                "action": ModuleSpec(kind="direct_answer"),
            },
            gates=GateConfig(),
        )
    )

    assert PassThroughPlan is FromModules
    assert isinstance(workflow.modules["plan"], PassThroughPlan)
    assert workflow.run("保固多久？").final_message == "本產品保固十二個月。"


# ---------------------------------------------------------------------------
# Planning and reflect exchange a bounded number of times, and planning reads
# what reflect reported.
# ---------------------------------------------------------------------------


class ReportingReflect:
    name = "reflect"

    def __call__(self, state):
        return ModuleOutput(
            next_module=None,
            payload={"reflect_verdict": "fail"},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.REFLECTION,
                    content="verdict=fail",
                    metadata={"verdict": "fail", "reason": "查到的是舊版條文", "suggestion": "改查新版條文"},
                )
            ],
        )


def _recording(client: FoundryOpenAILikeClient) -> list[dict]:
    requests: list[dict] = []
    original = client.chat.completions.create

    def create(**kwargs):
        requests.append(kwargs)
        return original(**kwargs)

    client.chat.completions.create = create
    return requests


def _system(request: dict) -> str:
    return request["messages"][0]["content"]


def _offered(request: dict) -> set[str]:
    line = next(line for line in _system(request).splitlines() if line.startswith("Choose next_module from:"))
    return {name.strip() for name in line.split(":", 1)[1].rstrip(".").split(",")}


def test_planning_and_reflect_exchange_at_most_five_times():
    plan = ScriptedPlan(["retrieve"] + ["reflect"] * 7)
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        plan=plan,
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
    )

    result = workflow.run("保固多久？")

    assert result.aborted is False
    assert result.visit_counts["reflect"] == 5
    assert result.final_message == "本產品保固十二個月。"
    assert plan.offered[-1] == ["retrieve", "action"]


def test_the_reflect_round_limit_can_be_changed():
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        plan=ScriptedPlan(["reflect"] * 4),
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
        gates=Gates(max_reflect_rounds=2),
    )

    result = workflow.run("保固多久？")

    assert result.aborted is False
    assert result.visit_counts["reflect"] == 2


def test_a_raised_reflect_round_limit_is_not_cut_short_by_the_revisit_limit():
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        plan=ScriptedPlan(["reflect"] * 9),
        retrieve=KeywordRetrieve(items=ITEMS),
        action=DirectAnswerAction(),
        reflect=RecordingReflect(),
        gates=Gates(max_reflect_rounds=7),
    )

    result = workflow.run("保固多久？")

    assert result.aborted is False
    assert result.visit_counts["reflect"] == 7


def test_workflow_config_carries_the_reflect_round_limit():
    workflow = build_workflow(WorkflowConfig(gates=GateConfig(max_reflect_rounds=3)))

    assert workflow.gates.max_reflect_rounds == 3
    assert Gates().max_reflect_rounds == 5


def test_next_step_plan_is_offered_only_the_steps_available_now():
    client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "reflect", "reflect", "action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=EvidenceCheckReflect(),
            gates=Gates(max_reflect_rounds=1),
        )

    workflow.run("保固多久？")

    assert [_offered(request) for request in requests] == [
        {"retrieve", "reflect", "action"},
        {"retrieve", "reflect", "action"},
        {"retrieve", "action"},
    ]


def test_next_step_plan_without_a_reflect_module_is_never_offered_reflect():
    client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
        )

    workflow.run("保固多久？")

    assert [_offered(request) for request in requests] == [{"retrieve", "action"}, {"retrieve", "action"}]
    assert all("reflect" not in _system(request) for request in requests)


def test_next_step_plan_is_told_what_the_mounted_reflect_module_is_for():
    client = FoundryOpenAILikeClient(plan_sequence=["action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=EvidenceCheckReflect(),
        )

    workflow.run("保固多久？")

    assert EvidenceCheckReflect.description
    assert EvidenceCheckReflect.description in _system(requests[0])


def test_a_reflect_description_replaces_the_modules_own():
    client = FoundryOpenAILikeClient(plan_sequence=["action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(reflect_description="確認查到的條文是最新版本", **LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=EvidenceCheckReflect(),
        )

    workflow.run("保固多久？")

    assert "確認查到的條文是最新版本" in _system(requests[0])
    assert EvidenceCheckReflect.description not in _system(requests[0])


def test_next_step_plan_reads_what_reflect_reported():
    client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "reflect", "action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=ReportingReflect(),
        )

    workflow.run("保固多久？")

    assert "查到的是舊版條文" not in _system(requests[1])
    assert "查到的是舊版條文" in _system(requests[2])
    assert "改查新版條文" in _system(requests[2])


def test_workflow_config_passes_a_reflect_description_to_next_step_plan():
    client = FoundryOpenAILikeClient(plan_sequence=["action"])
    requests = _recording(client)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = build_workflow(
            WorkflowConfig(
                modules={
                    "plan": ModuleSpec(kind="next_step", params={**LLM_PARAMS, "reflect_description": "確認條文版本"}),
                    "reflect": ModuleSpec(kind="evidence_check"),
                }
            )
        )

    workflow.run("保固多久？")

    assert "確認條文版本" in _system(requests[0])


# ---------------------------------------------------------------------------
# Reflect modules report what they found; they no longer decide the route.
# ---------------------------------------------------------------------------


def _reflection(result) -> ContextEntry:
    return [entry for entry in result.entries if entry.type == ContextEntryType.REFLECTION][-1]


def _evidence_agent(retrieve) -> Workflow:
    return Workflow(perceive=PassThroughPerceive(), retrieve=retrieve, action=DirectAnswerAction(), reflect=EvidenceCheckReflect())


def _plan_check_agent(reflect_client: FoundryOpenAILikeClient) -> Workflow:
    from agentic_sdk import PlanCheckReflect

    plan_client = FoundryOpenAILikeClient(plan_sequence=["retrieve", "reflect", "action"])
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", side_effect=[plan_client, reflect_client]):
        return Workflow(
            perceive=PassThroughPerceive(),
            plan=NextStepPlan(**LLM_PARAMS),
            retrieve=KeywordRetrieve(items=ITEMS),
            action=DirectAnswerAction(),
            reflect=PlanCheckReflect(**LLM_PARAMS),
        )


def test_reflect_modules_no_longer_choose_where_a_failure_goes():
    from agentic_sdk import PlanCheckReflect

    with pytest.raises(TypeError):
        EvidenceCheckReflect(on_failure="end")
    with pytest.raises(TypeError):
        PlanCheckReflect(on_failure="end", **LLM_PARAMS)


def test_evidence_check_reports_a_lookup_that_found_nothing():
    result = _evidence_agent(KeywordRetrieve(items=ITEMS)).run("退貨怎麼辦？")

    report = _reflection(result)
    assert result.entities["reflect_verdict"] == "fail"
    assert report.metadata["verdict"] == "fail"
    assert report.metadata["strategy"] == "evidence_check"
    assert report.metadata["reason"]


def test_evidence_check_passes_a_lookup_that_found_something():
    result = _evidence_agent(KeywordRetrieve(items=ITEMS)).run("保固多久？")

    assert result.entities["reflect_verdict"] == "pass"
    assert _reflection(result).metadata["verdict"] == "pass"


def test_evidence_check_passes_when_nothing_was_counted_and_says_why():
    counted = _reflection(_evidence_agent(KeywordRetrieve(items=ITEMS)).run("保固多久？"))
    uncounted = _reflection(_evidence_agent(PassThroughRetrieve()).run("用一句話說明什麼是保固。"))

    assert uncounted.metadata["verdict"] == "pass"
    assert uncounted.metadata["reason"]
    assert uncounted.metadata["reason"] != counted.metadata["reason"]


def test_plan_check_reads_the_plan_and_the_lookup_and_not_an_answer():
    reflect_client = FoundryOpenAILikeClient(
        reflect_verdict="fail",
        reflect_reason="規劃選的技能不存在",
        reflect_suggestion="先問使用者要用哪一套流程",
    )
    requests = _recording(reflect_client)

    result = _plan_check_agent(reflect_client).run("保固多久？")

    system = _system(requests[0])
    assert system.startswith("REFLECT")
    assert "route to reflect" in system
    assert "本產品保固十二個月。" in system
    assert "action_result" not in system
    # The check is about the step planning takes next, so it reads the steps
    # planning can choose from — not the decision that sent it here, which is
    # always "reflect".
    assert "retrieve, reflect, action" in system
    assert "plan_next_module: reflect" not in system
    assert _reflection(result).metadata == {
        "verdict": "fail",
        "reason": "規劃選的技能不存在",
        "suggestion": "先問使用者要用哪一套流程",
        "strategy": "plan_check",
    }
    assert result.entities["reflect_verdict"] == "fail"


def test_plan_check_lets_the_run_go_on_when_its_model_is_unavailable():
    reflect_client = FoundryOpenAILikeClient()
    reflect_client.chat.completions.create = _refuse

    result = _plan_check_agent(reflect_client).run("保固多久？")

    report = _reflection(result)
    assert report.metadata["verdict"] == "pass"
    assert "did not run" in report.metadata["reason"]
    assert "provider down" in report.metadata["reason"]
    assert result.final_message == "本產品保固十二個月。"


def test_plan_check_reflect_replaces_response_check_reflect():
    import agentic_sdk
    from agentic_sdk import PlanCheckReflect
    from agentic_sdk.modules import PlanCheckReflect as FromModules

    assert PlanCheckReflect is FromModules
    assert not hasattr(agentic_sdk, "ResponseCheckReflect")
    with pytest.raises(ImportError):
        from agentic_sdk.modules.reflect import ResponseCheckReflect  # noqa: F401


def test_workflow_config_builds_reflect_modules_by_their_kind_names():
    from agentic_sdk import PlanCheckReflect

    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient()):
        checked = build_workflow(WorkflowConfig(modules={"reflect": ModuleSpec(kind="plan_check", params=LLM_PARAMS)}))
    counted = build_workflow(WorkflowConfig(modules={"reflect": ModuleSpec(kind="evidence_check")}))

    assert isinstance(checked.modules["reflect"], PlanCheckReflect)
    assert isinstance(counted.modules["reflect"], EvidenceCheckReflect)
    with pytest.raises(ValueError, match="unsupported params"):
        build_workflow(WorkflowConfig(modules={"reflect": ModuleSpec(kind="evidence_check", params={"on_failure": "end"})}))
    with pytest.raises(ValueError, match="unknown module kind"):
        build_workflow(WorkflowConfig(modules={"reflect": ModuleSpec(kind="response_check", params=LLM_PARAMS)}))
