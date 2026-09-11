"""Playground agents close the loop through planning — ADR-0005.

Observed from Builder answers: the spec they produce, the Workflow
``build_workflow`` wires, what ``run_agent`` reports and the exported code.
"""

from __future__ import annotations

from agentic_sdk import PassThroughPlan, PlanCheckReflect, WorkflowResult
from agentic_sdk.core.events import default_events_schema
from playground.services import model_endpoints, runner_service
from playground.services.workflow_spec import compile_python_source, default_spec, validate_spec

from support import build_spec


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
