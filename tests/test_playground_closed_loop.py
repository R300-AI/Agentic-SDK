"""Playground agents close the loop through planning — ADR-0005.

Observed from Builder answers: the spec they produce, the Workflow
``build_workflow`` wires, what ``run_agent`` reports and the exported code.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest
from flask import session

from agentic_sdk import PassThroughPlan, PlanCheckReflect, WorkflowResult
from agentic_sdk.core import ContextEntry, ContextEntryType
from agentic_sdk.core.events import default_events_schema
from playground.app import create_app
from playground.services import model_endpoints, runner_service
from playground.services.aihub_bridge import store_loaded_agent
from playground.services.workflow_spec import compile_python_source, default_spec, spec_to_form_state, validate_spec

from support import FoundryOpenAILikeClient, build_spec


def _keyword_direct_agent(*extra):
    return build_spec(
        ("retrieve_policy", "keyword"),
        ("retrieve", {"keyword_pairs": "保固 = 本產品保固十二個月。"}),
        ("output_format", "direct"),
        *extra,
    )


def test_an_agent_nobody_gave_a_planner_still_plans():
    workflow = runner_service.build_workflow(_keyword_direct_agent(), {})

    assert isinstance(workflow.modules["plan"], PassThroughPlan)


def test_the_fixed_planning_rule_stays_out_of_the_process_panel():
    process_events: list[dict] = []

    result = runner_service.run_agent(
        _keyword_direct_agent(),
        message="保固多久？",
        endpoint_selections={},
        process_observer=process_events.append,
    )

    assert result["final_message"] == "本產品保固十二個月。"
    assert process_events
    assert [event for event in process_events if event["role"] == "plan"] == []


def test_exported_code_always_names_its_planning_module():
    fixed = compile_python_source(_keyword_direct_agent())
    modelled = compile_python_source(build_spec(("failure_policy", "retry")))

    assert "plan=PassThroughPlan()," in fixed
    assert "PassThroughPlan" in fixed.split("workflow = Workflow(")[0]
    assert "plan=NextStepPlan(" in modelled


def test_an_agent_carries_the_reflect_round_limit():
    spec = _keyword_direct_agent()

    assert spec["gates"]["max_reflect_rounds"] == 5
    assert runner_service.build_workflow(spec, {}).gates.max_reflect_rounds == 5
    limited = {**spec, "gates": {**spec["gates"], "max_reflect_rounds": 2}}
    assert runner_service.build_workflow(limited, {}).gates.max_reflect_rounds == 2


def test_a_stored_reflect_round_limit_is_kept_within_bounds():
    assert validate_spec({**default_spec(), "gates": {"max_reflect_rounds": 3}})["gates"]["max_reflect_rounds"] == 3
    assert validate_spec({**default_spec(), "gates": {"max_reflect_rounds": 0}})["gates"]["max_reflect_rounds"] == 5
    assert validate_spec({**default_spec(), "gates": {"max_reflect_rounds": 1000}})["gates"]["max_reflect_rounds"] == 100


def test_a_plan_that_chooses_reflect_says_it_checks_first(monkeypatch):
    schema = default_events_schema()["plan"]

    class FakeWorkflow:
        def run(self, *_args, event_callback=None, **_kwargs):
            event_callback(
                {
                    "type": "structured_field",
                    "phase": "field",
                    "status": "completed",
                    "module": "plan",
                    "module_class": "NextStepPlan",
                    "field": "next_module",
                    "value": "reflect",
                    "label": schema["label"],
                    "schema": schema,
                    "metadata": {},
                    "visit_id": "workflow-1:plan:2",
                }
            )
            return WorkflowResult(workflow_id="workflow-1", final_message="本產品保固十二個月。", visit_counts={"perceive": 1, "plan": 1, "action": 1})

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())
    process_events: list[dict] = []

    runner_service.run_agent(_keyword_direct_agent(), message="保固多久？", endpoint_selections={}, process_observer=process_events.append)

    assert "目前決定：先檢查。" in [event["description"] for event in process_events if event["role"] == "plan"]


def test_an_agent_that_looks_nothing_up_checks_its_plan_with_a_model():
    spec = build_spec(("failure_policy", "retry"))

    workflow = runner_service.build_workflow(spec, {"action": "gpt-54", "reflect": "gpt-54"})
    requirement = next(r for r in model_endpoints.endpoint_state(spec, {})["requirements"] if r["role"] == "reflect")

    assert isinstance(workflow.modules["reflect"], PlanCheckReflect)
    assert requirement["role_label"] == "規劃檢核器"
    assert requirement["module_name"] == "PlanCheckReflect"


def test_exported_reflect_modules_carry_no_failure_route():
    retry = compile_python_source(build_spec(("failure_policy", "retry")))
    handoff = compile_python_source(_keyword_direct_agent(("failure_policy", "handoff")))

    assert "reflect=PlanCheckReflect(" in retry
    assert "reflect=EvidenceCheckReflect()," in handoff
    for source in (retry, handoff):
        assert "on_failure" not in source
        assert "ResponseCheckReflect" not in source


def test_the_reflect_step_says_it_checks_the_plan_and_the_lookup():
    process_events: list[dict] = []

    runner_service.run_agent(
        _keyword_direct_agent(("failure_policy", "handoff")),
        message="保固多久？",
        endpoint_selections={},
        process_observer=process_events.append,
    )

    assert [event["description"] for event in process_events if event["role"] == "reflect"] == [
        "正在檢查規劃與查詢結果，確認可以開始回答。",
        "已檢查規劃與查詢結果。",
    ]


# ---------------------------------------------------------------------------
# Q5 installs planning and reflect by how the agent looks things up.
# ---------------------------------------------------------------------------

Q3_Q5_MAPPING = [
    ("none", "retry", "NextStepPlan", "PlanCheckReflect"),
    ("none", "handoff", "PassThroughPlan", None),
    ("keyword", "retry", "NextStepPlan", "EvidenceCheckReflect"),
    ("keyword", "handoff", "PassThroughPlan", "EvidenceCheckReflect"),
    ("semantic", "retry", "NextStepPlan", "EvidenceCheckReflect"),
    ("semantic", "handoff", "PassThroughPlan", "EvidenceCheckReflect"),
]


@pytest.mark.parametrize("lookup, answer, plan, reflect", Q3_Q5_MAPPING)
def test_q5_installs_planning_and_reflect_by_how_the_agent_looks_things_up(lookup, answer, plan, reflect):
    spec = build_spec(("retrieve_policy", lookup), ("failure_policy", answer))

    assert spec["plan"]["module"] == plan
    assert spec["reflect"]["module"] == reflect
    assert spec_to_form_state(spec)["choices"]["failure_policy"] == answer


@pytest.mark.parametrize("lookup, answer, plan, reflect", Q3_Q5_MAPPING)
def test_answering_q3_after_q5_installs_the_same_modules(lookup, answer, plan, reflect):
    other = "none" if lookup != "none" else "keyword"
    spec = build_spec(("retrieve_policy", other), ("failure_policy", answer), ("retrieve_policy", lookup))

    assert spec["plan"]["module"] == plan
    assert spec["reflect"]["module"] == reflect
    assert spec_to_form_state(spec)["choices"]["failure_policy"] == answer


@pytest.mark.parametrize("lookup", ["none", "keyword", "semantic"])
def test_q3_alone_installs_no_planning_module(lookup):
    spec = build_spec(("retrieve_policy", lookup))

    assert spec["plan"]["module"] is None
    assert spec["reflect"]["module"] is None
    assert spec_to_form_state(spec)["choices"]["failure_policy"] == ""


def test_a_spec_stores_no_failure_route_and_no_plan_strategy():
    spec = build_spec(("retrieve_policy", "keyword"), ("failure_policy", "retry"))

    assert "on_failure" not in spec["reflect"]["params"]
    assert "strategy" not in spec["plan"]["params"]
    assert "on_failure" not in default_spec()["reflect"]["params"]
    assert "strategy" not in default_spec()["plan"]["params"]


@pytest.mark.parametrize("lookup, answer, plan, reflect", Q3_Q5_MAPPING)
def test_exported_code_names_the_mapped_modules(lookup, answer, plan, reflect):
    source = compile_python_source(build_spec(("retrieve_policy", lookup), ("failure_policy", answer)))

    assert f"plan={plan}(" in source
    if reflect is None:
        assert "reflect=" not in source
    else:
        assert f"reflect={reflect}(" in source


def test_an_agent_that_looks_nothing_up_and_stops_needs_no_checker_model():
    spec = build_spec(("retrieve_policy", "none"), ("failure_policy", "handoff"))

    assert "reflect" not in [r["role"] for r in model_endpoints.endpoint_state(spec, {})["requirements"]]


def _retrying_keyword_agent():
    return build_spec(
        ("retrieve_policy", "keyword"),
        ("retrieve", {"keyword_pairs": "保固 = 本產品保固十二個月。"}),
        ("output_format", "direct"),
        ("failure_policy", "retry"),
    )


def _run_with_planner(spec, plan_sequence, message="保固多久？"):
    client = FoundryOpenAILikeClient(plan_sequence=plan_sequence)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = runner_service.build_workflow(spec, {"action": "gpt-54"})
    events: list[dict] = []
    result = workflow.run(message, event_callback=events.append)
    stages = [event["stage"] for event in events if event.get("type") == "stage" and event["phase"] == "start"]
    return result, stages


def test_a_retrying_agent_looks_up_first_and_checks_the_lookup_before_answering():
    result, stages = _run_with_planner(_retrying_keyword_agent(), ["action"])

    assert stages == ["perceive", "plan", "retrieve", "plan", "reflect", "plan", "action"]
    assert result.final_message == "本產品保固十二個月。"


def test_a_retrying_agent_looks_again_at_most_once_and_checks_each_lookup():
    result, stages = _run_with_planner(_retrying_keyword_agent(), ["retrieve"])

    assert stages == [
        "perceive", "plan", "retrieve", "plan", "reflect", "plan", "retrieve", "plan", "reflect", "plan", "action",
    ]
    assert result.aborted is False


def _fake_run(monkeypatch, entries, final_message="沒有命中任何條目。"):
    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message=final_message, entries=list(entries), entities={})

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_args, **_kwargs: FakeWorkflow())


MISSED = ContextEntry(type=ContextEntryType.RETRIEVED, content="沒有命中任何條目。", metadata={"source": "keyword_retrieve", "hit_count": 0})
PASSED = ContextEntry(type=ContextEntryType.REFLECTION, content="verdict=pass", metadata={"verdict": "pass", "reason": "ok", "strategy": "evidence_check"})
FAILED = ContextEntry(type=ContextEntryType.REFLECTION, content="verdict=fail", metadata={"verdict": "fail", "reason": "no retrieved evidence", "strategy": "evidence_check"})


def test_a_stopping_agent_hands_over_when_reflect_reports_a_failure(monkeypatch):
    _fake_run(monkeypatch, [MISSED, FAILED])

    result = runner_service.run_agent(_keyword_direct_agent(("failure_policy", "handoff")), message="退貨怎麼辦？", endpoint_selections={})

    assert "已停止作答" in result["final_message"]
    assert result["status"] == "aborted"


def test_the_handoff_follows_what_reflect_reported_not_the_hit_count(monkeypatch):
    _fake_run(monkeypatch, [MISSED, PASSED])

    result = runner_service.run_agent(_keyword_direct_agent(("failure_policy", "handoff")), message="退貨怎麼辦？", endpoint_selections={})

    assert result["final_message"] == "沒有命中任何條目。"


def test_a_retrying_agent_never_hands_over(monkeypatch):
    _fake_run(monkeypatch, [MISSED, FAILED])

    result = runner_service.run_agent(_retrying_keyword_agent(), message="請推薦產品編號 X-UNKNOWN-999", endpoint_selections={})

    assert "已停止作答" not in result["final_message"]
    assert "人工確認" not in result["final_message"]


def test_a_stopping_agent_really_runs_and_hands_over_on_an_empty_lookup():
    result = runner_service.run_agent(_keyword_direct_agent(("failure_policy", "handoff")), message="退貨怎麼辦？", endpoint_selections={})

    assert "已停止作答" in result["final_message"]


# ---------------------------------------------------------------------------
# Agents saved by 0.2.0 read back in the new format.
# ---------------------------------------------------------------------------


def _as_saved_by_0_2_0(spec, *, plan_module, strategy, reflect_module, on_failure):
    saved = copy.deepcopy(spec)
    saved["plan"] = {"module": plan_module, "params": {"strategy": strategy, "system_prompt": None}}
    saved["reflect"] = {"module": reflect_module, "params": {"on_failure": on_failure}}
    return saved


SAVED_BY_0_2_0 = [
    # lookup, saved plan, strategy, saved reflect, on_failure → Q5 answer, plan, reflect
    ("keyword", None, None, "EvidenceCheckReflect", "end", "handoff", "PassThroughPlan", "EvidenceCheckReflect"),
    ("keyword", "NextStepPlan", "RouteBySupport", "EvidenceCheckReflect", "retry_plan", "retry", "NextStepPlan", "EvidenceCheckReflect"),
    ("semantic", "NextStepPlan", "RouteBySupport", "EvidenceCheckReflect", "end", "handoff", "PassThroughPlan", "EvidenceCheckReflect"),
    ("none", "NextStepPlan", "RouteBySupport", "ResponseCheckReflect", "retry_plan", "retry", "NextStepPlan", "PlanCheckReflect"),
    ("none", None, None, "ResponseCheckReflect", "end", "handoff", "PassThroughPlan", None),
    ("semantic", "NextStepPlan", "RouteBySupport", None, None, "", None, None),
]


@pytest.mark.parametrize("lookup, saved_plan, strategy, saved_reflect, on_failure, answer, plan, reflect", SAVED_BY_0_2_0)
def test_an_agent_saved_by_0_2_0_reads_back_its_q5_answer(lookup, saved_plan, strategy, saved_reflect, on_failure, answer, plan, reflect):
    saved = _as_saved_by_0_2_0(
        build_spec(("retrieve_policy", lookup)),
        plan_module=saved_plan,
        strategy=strategy,
        reflect_module=saved_reflect,
        on_failure=on_failure,
    )

    spec = validate_spec(saved)

    assert spec["plan"]["module"] == plan
    assert spec["reflect"]["module"] == reflect
    assert spec_to_form_state(spec)["choices"]["failure_policy"] == answer
    assert "strategy" not in spec["plan"]["params"]
    assert "on_failure" not in spec["reflect"]["params"]


def test_an_agent_saved_by_0_2_0_still_answers_and_still_hands_over():
    saved = _as_saved_by_0_2_0(
        _keyword_direct_agent(),
        plan_module=None,
        strategy=None,
        reflect_module="EvidenceCheckReflect",
        on_failure="end",
    )
    spec = validate_spec(saved)

    answered = runner_service.run_agent(spec, message="保固多久？", endpoint_selections={})
    handed_over = runner_service.run_agent(spec, message="退貨怎麼辦？", endpoint_selections={})

    assert answered["final_message"] == "本產品保固十二個月。"
    assert "已停止作答" in handed_over["final_message"]


def test_an_agent_loaded_from_ai_hub_is_held_in_the_new_format():
    saved = _as_saved_by_0_2_0(
        _keyword_direct_agent(),
        plan_module=None,
        strategy=None,
        reflect_module="EvidenceCheckReflect",
        on_failure="end",
    )
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_request_context():
        store_loaded_agent({"agent_id": "agent-1", "agent_name": "舊版 agent", "endpoint_bindings": {}, "workflow_spec": saved, "runner_presentation": {}})
        held = session["workflow_spec"]

    assert held["plan"] == {"module": "PassThroughPlan", "params": {"system_prompt": None}}
    assert held["reflect"] == {"module": "EvidenceCheckReflect", "params": {}}


@pytest.mark.parametrize("lookup, answer, plan, reflect", Q3_Q5_MAPPING)
def test_a_spec_in_the_new_format_reads_back_unchanged(lookup, answer, plan, reflect):
    spec = validate_spec(build_spec(("retrieve_policy", lookup), ("failure_policy", answer)))

    assert spec["plan"]["module"] == plan
    assert spec["reflect"]["module"] == reflect
    assert spec_to_form_state(spec)["choices"]["failure_policy"] == answer
