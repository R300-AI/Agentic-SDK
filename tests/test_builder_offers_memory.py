"""Choosing, in the builder, whether an agent carries things between conversations.

Q1 has always shown the choice and always refused it. What the person on the
floor answers here decides three things: which memory the agent keeps, whether
it collects its oldest exchanges into topics, and how long a conversation is
allowed to get before it does.

Where the memory writes and which endpoint collects for it are not asked. The
first is a property of the machine it runs on, which the person answering Q1
has no way to know; the second goes the way every other endpoint goes.
"""

from __future__ import annotations

from pathlib import Path

from playground.services.model_endpoints import openai_requirements_from_spec
from playground.services.source_builder import get_builder_steps
from support import build_spec

from playground.services.workflow_spec import (
    apply_builder_step,
    default_spec,
    spec_to_form_state,
    validate_spec,
)


def _q1():
    return next(step for step in get_builder_steps() if step.key == "memory_type")


def _choice(label: str):
    return next(choice for choice in _q1().choices if choice.label == label)


def _answered(**answer):
    return apply_builder_step(default_spec(), "memory_type", answer)


def _runnable(**answer):
    """A spec complete enough to build, so the memory is what is being watched."""
    return validate_spec(build_spec(("memory_type", answer)))


# --- the choice itself ---------------------------------------------------


def test_carrying_things_between_conversations_can_be_chosen():
    choice = _choice("cross_context")

    assert choice.available, "a choice shown and refused tells the floor the product cannot do this"
    assert not choice.badge, "and a badge saying it is coming is wrong once it is here"


def test_the_memory_that_keeps_nothing_after_a_restart_is_not_offered():
    labels = {choice.label for choice in _q1().choices}

    assert labels == {"in_context", "cross_context"}, (
        "somebody who picks 承接前文問答 and loses everything on restart was told the wrong thing; "
        "keeping it in memory is a fallback, not something to choose"
    )


def test_the_choice_names_what_the_memory_does_and_not_where_it_writes():
    spec = _answered(kind="cross_context")

    assert spec["memory"]["kind"] == "cross_context", (
        "a spec saved this year must still open next year, after the storage has changed"
    )


# --- what is asked under the same question -------------------------------


def test_collecting_old_exchanges_is_asked_about_under_the_same_question():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)

    assert spec["memory"]["params"]["compaction_threshold_tokens"] == 4000


def test_collecting_is_off_until_somebody_turns_it_on():
    spec = _answered(kind="cross_context")

    assert spec["memory"]["params"].get("compaction_threshold_tokens") is None, (
        "collecting costs a model call while somebody waits for an answer"
    )


def test_turning_collecting_off_removes_the_threshold_rather_than_keeping_it():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)
    spec = apply_builder_step(spec, "memory_type", {"kind": "cross_context", "compaction_enabled": False})

    assert spec["memory"]["params"].get("compaction_threshold_tokens") is None, (
        "a threshold left behind is a switch that says off and behaves on"
    )


def test_a_threshold_nobody_can_answer_with_falls_back_to_a_usable_one():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens="很多")

    threshold = spec["memory"]["params"]["compaction_threshold_tokens"]
    assert isinstance(threshold, int) and threshold > 0, (
        "a typed answer that is not a number must not leave the agent unable to start"
    )


def test_going_back_to_this_conversation_only_drops_what_it_cannot_use():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)
    spec = apply_builder_step(spec, "memory_type", {"kind": "in_context"})

    assert spec["memory"]["kind"] == "in_context"
    assert not spec["memory"].get("params"), (
        "a memory that only sees this conversation has nothing to collect"
    )


# --- the answer survives being saved and reopened ------------------------


def test_what_was_answered_comes_back_when_the_agent_is_reopened():
    spec = validate_spec(_answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000))

    state = spec_to_form_state(spec)

    assert state["choices"]["memory_type"] == "cross_context"
    assert state["values"]["memory_type"]["compaction_threshold_tokens"] == "4000"
    assert state["values"]["memory_type"]["compaction_enabled"] == "on"


def test_a_saved_agent_that_never_answered_this_still_opens():
    state = spec_to_form_state(validate_spec(default_spec()))

    assert state["choices"]["memory_type"] == "in_context"


# --- what the deployment has to supply -----------------------------------


def test_collecting_asks_the_deployment_for_an_endpoint():
    spec = validate_spec(_answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000))

    roles = {requirement["role"] for requirement in openai_requirements_from_spec(spec)}

    assert "memory" in roles, (
        "collecting old exchanges into a topic is a model call, so it needs an endpoint bound "
        "to it like every other model call"
    )


def test_a_memory_that_does_not_collect_asks_for_no_endpoint():
    spec = validate_spec(_answered(kind="cross_context"))

    roles = {requirement["role"] for requirement in openai_requirements_from_spec(spec)}

    assert "memory" not in roles, (
        "carrying things between conversations needs no model; only collecting them does"
    )


def test_where_the_memory_writes_is_not_something_the_floor_is_asked():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000, root="C:/somewhere")

    assert "root" not in spec["memory"]["params"], (
        "which directory a server keeps files in is a property of that server, and the person "
        "answering Q1 is not at that server"
    )


# --- what the runner builds from the answer ------------------------------


def test_the_agent_runs_with_the_memory_that_was_chosen(tmp_path, monkeypatch):
    from agentic_sdk import FileMemoryStore
    from playground.services import runner_service

    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))
    memory = runner_service.build_workflow(_runnable(kind="cross_context"), {}).memory_type

    assert isinstance(memory, FileMemoryStore), "carrying things between conversations means writing them down"
    assert memory.root == tmp_path


def test_where_the_memory_writes_comes_from_the_machine_it_runs_on(monkeypatch):
    from playground.services import runner_service

    monkeypatch.delenv("PLAYGROUND_MEMORY_ROOT", raising=False)
    memory = runner_service.build_workflow(_runnable(kind="cross_context"), {}).memory_type

    assert memory.root.exists(), (
        "a deployment that has said nothing still starts, in a place the machine has"
    )


def test_an_agent_that_only_sees_this_conversation_writes_nothing_down(tmp_path, monkeypatch):
    from agentic_sdk import InContextMemory
    from playground.services import runner_service

    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))

    memory = runner_service.build_workflow(_runnable(kind="in_context"), {}).memory_type

    assert memory is InContextMemory
    assert not list(tmp_path.iterdir()), "nothing was asked to be kept, so nothing is kept"


def test_the_endpoint_bound_to_the_memory_is_the_one_it_collects_with(tmp_path, monkeypatch):
    from playground.services import runner_service

    monkeypatch.setenv("PLAYGROUND_TEST_MODE", "1")
    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))
    spec = _runnable(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)

    memory = runner_service.build_workflow(spec, {"memory": "gpt-54"}).memory_type

    assert memory.compaction_threshold_tokens == 4000
    assert memory._model == "gpt-5.4", (
        "collecting runs on the endpoint somebody bound to it, not on the one the answer uses"
    )


def test_typing_a_starter_question_does_not_change_which_memory_was_chosen():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)

    spec = apply_builder_step(spec, "memory_type", {"compaction_enabled": "on", "compaction_threshold_tokens": "4000"})

    assert spec["memory"]["kind"] == "cross_context", (
        "the form under a question carries that question's settings; the choice is posted when "
        "it is clicked, so a form that does not mention it must not decide it"
    )


# --- the page asks with the names the service answers to -----------------


def _memory_form_field_names() -> set[str]:
    """The fields the Q1 form posts, read off the page itself."""
    import re

    page = (Path(__file__).resolve().parents[1] / "playground" / "templates" / "builder.html").read_text(encoding="utf-8")
    form = page.split('data-step-key="memory_type"', 1)[1].split("</form>", 1)[0]
    return set(re.findall(r'name="([^"]+)"', form))


def test_the_page_asks_for_collecting_with_the_names_the_spec_reads():
    names = _memory_form_field_names()

    assert {"compaction_enabled", "compaction_threshold_tokens"} <= names, (
        "a question the page does not ask is a setting nobody can reach, however well the "
        "service handles it"
    )


def test_the_collecting_fields_are_shown_only_for_the_memory_that_collects():
    page = (Path(__file__).resolve().parents[1] / "playground" / "templates" / "builder.html").read_text(encoding="utf-8")
    form = page.split('data-step-key="memory_type"', 1)[1].split("</form>", 1)[0]
    assert 'data-visible-choices="cross_context"' in form, "nothing on the page is shown for it"
    block = form.split('data-visible-choices="cross_context"', 1)[1].split("</div>", 1)[0]

    assert "compaction_threshold_tokens" in block, (
        "a memory that only sees this conversation has nothing to collect, so asking would "
        "be asking about something that cannot happen"
    )


def test_the_exported_code_keeps_the_memory_the_agent_was_built_with():
    from playground.services.workflow_spec import compile_python_source

    source = compile_python_source(build_spec(("memory_type", {"kind": "cross_context"})))

    assert "memory_type=FileMemoryStore(" in source, (
        "an agent built to carry things over, copied out and run elsewhere, must not quietly "
        "carry nothing"
    )
    assert "from agentic_sdk import FileMemoryStore" in source, "and the export must run as it stands"


def test_the_exported_code_says_nothing_about_memory_when_none_was_asked_for():
    from playground.services.workflow_spec import compile_python_source

    source = compile_python_source(build_spec(("memory_type", {"kind": "in_context"})))

    assert "memory_type" not in source, (
        "seeing only this conversation is what a Workflow does unasked, so naming it adds a "
        "line that changes nothing"
    )


def test_a_memory_with_nowhere_to_write_does_not_refuse_a_setting_it_was_offered():
    from agentic_sdk import MemorySpec, build_memory

    memory = build_memory(MemorySpec(kind="cross_context", params={"raw_retention_seconds": 60}))

    assert memory is not None, (
        "the whitelist accepted that setting, so the build must not then reject it by name"
    )


def test_typing_a_starter_question_does_not_turn_collecting_off():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)

    # What the page actually posts once the route has taken the starter
    # question out: a dict that says nothing about the switch.
    spec = apply_builder_step(spec, "memory_type", {})

    assert spec["memory"]["params"].get("compaction_threshold_tokens") == 4000, (
        "only the form carrying the switch may turn it off; a post about something else "
        "under the same question must leave it alone"
    )


def test_switching_memory_kind_does_not_carry_settings_over():
    spec = _answered(kind="cross_context", compaction_enabled=True, compaction_threshold_tokens=4000)

    spec = apply_builder_step(spec, "memory_type", {"kind": "in_context"})

    assert not spec["memory"]["params"], "a memory that only sees this conversation has nothing to collect"
