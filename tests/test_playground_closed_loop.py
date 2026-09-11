"""Playground agents close the loop through planning — ADR-0005.

Observed from Builder answers: the spec they produce, the Workflow
``build_workflow`` wires, what ``run_agent`` reports and the exported code.
"""

from __future__ import annotations

from agentic_sdk import PassThroughPlan
from playground.services import runner_service
from playground.services.workflow_spec import compile_python_source

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
