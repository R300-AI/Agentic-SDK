"""An agent in the Playground mounts skill packages — ADR-0006.

Observed from the Builder's answers: the spec they produce, the workflow
``build_workflow`` wires, what ``run_agent`` reports, and the exported code.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from agentic_sdk.modules import NextStepWithSkills, PassThroughPlan
from playground.services import runner_service, skill_store
from playground.services.workflow_spec import compile_python_source, default_spec, spec_to_config, validate_spec

from support import build_spec, write_skill_package


@pytest.fixture()
def store(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("PLAYGROUND_SKILL_STORE_ROOT", str(tmp_path / "store"))
    return tmp_path


def _zip_of(package: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                archive.write(file, Path(package.name, file.relative_to(package)).as_posix())
    return buffer.getvalue()


def _mount(package: Path, spec: dict) -> dict:
    """Put a package through the store the way the Builder does, and mount it."""
    staging_id = skill_store.stage_upload(_zip_of(package), f"{package.name}.zip")
    entry = skill_store.commit(staging_id, skill_store.mounted_entries(spec))
    return skill_store.with_entry(spec, entry)


def _meeting_package(root: Path) -> Path:
    return write_skill_package(
        root,
        "meeting-notes",
        skills={
            "minutes": {"description": "把逐字稿整理成會議紀錄", "body": "先確認會議主題。", "prompts": ["format.md"]},
            "action-items": {"description": "列出待辦事項與負責人", "body": "每一項都要對得上原文。"},
        },
        prompts={"format.md": "## 會議資訊\n- 主題：\n"},
    )


def _agent_with_skills(store: Path, *steps) -> dict:
    spec = build_spec(*steps)
    return _mount(_meeting_package(store / "packages"), spec)


def test_an_agent_records_which_packages_it_mounts(store) -> None:
    spec = _agent_with_skills(store)

    entries = spec["skills"]["packages"]

    assert [entry["name"] for entry in entries] == ["meeting-notes"]
    assert entries[0]["source"] == "upload"
    assert len(entries[0]["digest"]) == 64


def test_mounting_a_package_settles_which_planning_module_runs(store) -> None:
    """Whatever Q5 answered: only the planning module with a model can pick a skill."""
    stopping = _agent_with_skills(store, ("retrieve_policy", "keyword"), ("output_format", "direct"), ("failure_policy", "handoff"))

    assert stopping["plan"]["module"] == "PassThroughPlan"
    assert spec_to_config(stopping).plan_module == "NextStepWithSkills"

    workflow = runner_service.build_workflow(stopping, {"action": "gpt-54"})

    assert isinstance(workflow.modules["plan"], NextStepWithSkills)
    assert [skill.name for skill in workflow.modules["plan"].skills] == ["minutes", "action-items"]


def test_an_agent_with_no_packages_plans_as_before(store) -> None:
    spec = build_spec(("retrieve_policy", "keyword"), ("output_format", "direct"), ("failure_policy", "handoff"))

    assert spec_to_config(spec).plan_module == "PassThroughPlan"
    assert isinstance(runner_service.build_workflow(spec, {}).modules["plan"], PassThroughPlan)


def test_the_skills_reach_the_planning_module_with_their_content(store) -> None:
    spec = _agent_with_skills(store)

    skills = runner_service.build_workflow(spec, {"action": "gpt-54"}).modules["plan"].skills

    minutes = next(skill for skill in skills if skill.name == "minutes")
    assert minutes.sections() == ["先確認會議主題。", "## 會議資訊\n- 主題："]


def test_an_agent_whose_package_is_not_on_this_server_says_so_before_running(store) -> None:
    spec = _agent_with_skills(store)
    entry = spec["skills"]["packages"][0]
    gone = {**spec, "skills": {"packages": [{**entry, "digest": "b" * 64}]}}

    result = runner_service.run_agent(gone, message="整理這段逐字稿", endpoint_selections={"action": "gpt-54"})

    assert result["status"] == "configuration_error"
    assert "meeting-notes" in result["final_message"]


def test_a_stored_spec_keeps_only_entries_that_could_name_a_package(store) -> None:
    spec = _agent_with_skills(store)
    entry = spec["skills"]["packages"][0]
    raw = {
        **spec,
        "skills": {
            "packages": [
                entry,
                {**entry, "name": "no-digest", "digest": ""},
                {**entry, "name": "no-version", "version": ""},
                "not-a-mapping",
            ]
        },
    }

    kept = validate_spec(raw)["skills"]["packages"]

    assert [item["name"] for item in kept] == ["meeting-notes"]
    assert validate_spec(default_spec())["skills"] == {"packages": []}


def test_exported_code_mounts_the_packages_on_the_planning_module(store) -> None:
    spec = _agent_with_skills(store, ("retrieve_policy", "keyword"), ("output_format", "direct"), ("failure_policy", "handoff"))

    source = compile_python_source(spec)

    assert "plan=NextStepWithSkills(" in source
    assert '"skill_packages/meeting-notes"' in source
