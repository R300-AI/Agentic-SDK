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
from playground.app import create_app
from playground.routes import builder as builder_routes
from playground.services import runner_service, skill_store
from playground.services.source_builder import get_builder_steps
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
    assert validate_spec(default_spec())["skills"] == {"packages": [], "declared": False}


def test_exported_code_mounts_the_packages_on_the_planning_module(store) -> None:
    spec = _agent_with_skills(store, ("retrieve_policy", "keyword"), ("output_format", "direct"), ("failure_policy", "handoff"))

    source = compile_python_source(spec)

    assert "plan=NextStepWithSkills(" in source
    assert '"skill_packages/meeting-notes"' in source


@pytest.fixture()
def client(store):
    """A Playground served by the app itself, so the routes are what is observed."""
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def _answer_standard_procedure(client, choice: str):
    return client.post("/playground/builder/state", json={"step": "standard_procedure", "choice": choice})


def test_the_builder_asks_about_standard_procedure_before_the_last_step(client) -> None:
    page = client.get("/playground/builder").get_data(as_text=True)

    assert "固定的標準作業流程" in page
    assert "data-skill-package-panel" in page
    steps = [step.key for step in get_builder_steps()]
    assert steps[steps.index("failure_policy") + 1 :] == ["standard_procedure", "readiness"]


def test_answering_no_standard_procedure_counts_as_answered(client) -> None:
    before = _review_item(client, "standard_procedure")
    assert before["completed"] is False

    _answer_standard_procedure(client, "none")

    after = _review_item(client, "standard_procedure")
    assert after["completed"] is True
    assert "沒有" in after["answer"]


def _review_item(client, step_key: str) -> dict:
    page = client.get("/playground/builder")
    items = builder_routes._builder_review_payload(
        get_builder_steps(),
        builder_routes._builder_form_state_from_spec(_spec_in(client)),
        {},
    )["items"]
    assert page.status_code == 200
    return next(item for item in items if item["step_key"] == step_key)


def _spec_in(client) -> dict:
    with client.session_transaction() as session:
        return session.get("workflow_spec") or default_spec()


def test_a_package_is_inspected_before_it_is_mounted(client, store) -> None:
    package = _meeting_package(store / "packages")

    preview = client.post(
        "/playground/builder/skills/inspect",
        data={"package": (io.BytesIO(_zip_of(package)), "meeting-notes.zip")},
        content_type="multipart/form-data",
    )

    assert preview.status_code == 200
    described = preview.json["package"]
    assert [skill["name"] for skill in described["skills"]] == ["minutes", "action-items"]
    assert described["skills"][0]["description"] == "把逐字稿整理成會議紀錄"
    assert described["version"]
    # Inspecting shows what would be added; nothing is mounted yet.
    assert client.get("/playground/builder/skills").json["packages"] == []


def test_a_package_that_breaks_a_rule_says_which_rule_and_which_file(client, store) -> None:
    broken = write_skill_package(
        store / "broken",
        "broken-package",
        skills={"lonely": {"description": "說明", "body": "內容", "prompts": ["missing.md"]}},
    )

    refusal = client.post(
        "/playground/builder/skills/inspect",
        data={"package": (io.BytesIO(_zip_of(broken)), "broken-package.zip")},
        content_type="multipart/form-data",
    )

    assert refusal.status_code == 422
    assert refusal.json["refused"]["rule"] == "missing_file"
    assert "missing.md" in refusal.json["refused"]["path"]


def test_mounting_then_removing_a_package_through_the_builder(client, store) -> None:
    package = _meeting_package(store / "packages")
    preview = client.post(
        "/playground/builder/skills/inspect",
        data={"package": (io.BytesIO(_zip_of(package)), "meeting-notes.zip")},
        content_type="multipart/form-data",
    )

    mounted = client.post("/playground/builder/skills/mount", json={"staging_id": preview.json["staging_id"]})

    assert [item["name"] for item in mounted.json["packages"]] == ["meeting-notes"]
    assert _review_item(client, "standard_procedure")["completed"] is True
    assert client.get("/playground/run/skills").json["skills"][0]["name"] == "minutes"

    removed = client.post("/playground/builder/skills/remove", json={"name": "meeting-notes"})

    assert removed.json["packages"] == []
    assert client.get("/playground/run/skills").json["skills"] == []


def test_the_slash_menu_is_empty_for_an_agent_with_no_packages(client) -> None:
    assert client.get("/playground/run/skills").json == {"skills": []}


def test_the_code_preview_carries_the_packages_the_code_names(client, store) -> None:
    package = _meeting_package(store / "packages")
    preview = client.post(
        "/playground/builder/skills/inspect",
        data={"package": (io.BytesIO(_zip_of(package)), "meeting-notes.zip")},
        content_type="multipart/form-data",
    )
    client.post("/playground/builder/skills/mount", json={"staging_id": preview.json["staging_id"]})

    markdown = client.get("/playground/source/preview").get_data(as_text=True)
    download = client.get("/playground/source/skill-packages.zip")

    assert "skill_packages/meeting-notes" in markdown
    assert "meeting-notes" in markdown and "minutes" in markdown
    assert "/playground/source/skill-packages.zip" in markdown
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        assert "skill_packages/meeting-notes/skills/minutes/SKILL.md" in archive.namelist()


def test_an_agent_with_no_packages_has_nothing_to_download(client) -> None:
    markdown = client.get("/playground/source/preview").get_data(as_text=True)

    assert "技能包" not in markdown
    assert client.get("/playground/source/skill-packages.zip").status_code == 404


def test_an_agent_is_told_when_it_has_mounted_as_many_packages_as_it_may(client, store) -> None:
    """The ceiling refuses in the open, rather than dropping entries when the spec is stored."""
    full = [{"name": f"package-{index:02d}", "source": "upload", "url": None, "version": "v1", "digest": str(index).zfill(64)} for index in range(20)]
    with client.session_transaction() as session:
        session["workflow_spec"] = {**default_spec(), "skills": {"packages": full, "declared": True}}
    package = _meeting_package(store / "packages")
    preview = client.post(
        "/playground/builder/skills/inspect",
        data={"package": (io.BytesIO(_zip_of(package)), "meeting-notes.zip")},
        content_type="multipart/form-data",
    )

    refused = client.post("/playground/builder/skills/mount", json={"staging_id": preview.json["staging_id"]})

    assert refused.status_code == 422
    assert refused.json["refused"]["rule"] == "too_many_packages"
