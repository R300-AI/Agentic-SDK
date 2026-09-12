"""Where a skill package comes from — ADR-0007.

Observed through ``mount_packages`` and the planning module that takes the
sources: what a source resolves to, and what it is refused for.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from agentic_sdk.skills import SkillSourceRefused, fetch_git_package, mount_packages

from support import write_skill_package


@pytest.fixture()
def cache(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "cache"
    monkeypatch.setenv("AGENTIC_SDK_SKILL_PACKAGES", str(root))
    return root


def _package(root: Path, name: str = "proposal", skill: str = "write") -> Path:
    return write_skill_package(root, name, skills={skill: {"description": "把計畫書的一章寫出來", "body": "先確認章節目標。"}})


def _zip_of(package: Path, target: Path) -> Path:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                archive.write(file, Path(package.name, file.relative_to(package)).as_posix())
    return target


def _repository(root: Path, package: Path, version: str) -> str:
    """A real git repository holding the package, addressed as a file URL."""
    # A repository is the package, so it is named after it.
    work = root / package.name
    work.mkdir(parents=True)
    for file in sorted(package.rglob("*")):
        if file.is_file():
            target = work / file.relative_to(package)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file.read_bytes())
    commands = (
        ["git", "init", "--quiet", "--initial-branch", "main"],
        ["git", "-c", "user.email=t@test", "-c", "user.name=T", "add", "."],
        ["git", "-c", "user.email=t@test", "-c", "user.name=T", "commit", "--quiet", "-m", "package"],
        ["git", "tag", version],
    )
    for command in commands:
        subprocess.run(command, cwd=work, check=True, capture_output=True)
    return f"file://{work}"


def test_a_directory_is_mounted_as_it_is(tmp_path, cache) -> None:
    mounted = mount_packages([_package(tmp_path)])

    assert [skill.name for skill in mounted[0].skills] == ["write"]


def test_one_source_does_not_have_to_be_written_as_a_list(tmp_path, cache) -> None:
    """A bare string is one source, not a sequence of characters."""
    mounted = mount_packages(str(_package(tmp_path)))

    assert [package.name for package in mounted] == ["proposal"]


def test_a_zip_archive_is_unpacked_and_mounted(tmp_path, cache) -> None:
    archive = _zip_of(_package(tmp_path / "authored"), tmp_path / "proposal.zip")

    mounted = mount_packages([archive])

    assert [package.name for package in mounted] == ["proposal"]
    assert [skill.name for skill in mounted[0].skills] == ["write"]


def test_a_repository_at_a_version_is_fetched_and_mounted(tmp_path, cache) -> None:
    url = _repository(tmp_path / "remote", _package(tmp_path / "authored", "meeting-notes"), "v1.2.0")

    mounted = mount_packages([f"{url}@v1.2.0"])

    assert [package.name for package in mounted] == ["meeting-notes"]
    assert [skill.name for skill in mounted[0].skills] == ["write"]
    assert cache.exists()


def test_a_package_already_fetched_is_not_fetched_again(tmp_path, cache, monkeypatch) -> None:
    """A workflow that ran once still starts when the repository is gone."""
    url = _repository(tmp_path / "remote", _package(tmp_path / "authored", "meeting-notes"), "v1.2.0")
    mount_packages([f"{url}@v1.2.0"])

    def refuse_to_fetch(*args, **kwargs):
        raise AssertionError("the package is already here; nothing should be fetched")

    monkeypatch.setattr("agentic_sdk.skills.source.fetch_git_package", refuse_to_fetch)

    mounted = mount_packages([f"{url}@v1.2.0"])

    assert [package.name for package in mounted] == ["meeting-notes"]


def test_paths_and_addresses_mount_together(tmp_path, cache) -> None:
    url = _repository(tmp_path / "remote", _package(tmp_path / "authored", "meeting-notes", "minutes"), "v1.2.0")
    local = _package(tmp_path / "local", "proposal")

    mounted = mount_packages([f"{url}@v1.2.0", local])

    assert [package.name for package in mounted] == ["meeting-notes", "proposal"]


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("https://github.com/org/skills.git", "missing_version"),
        ("http://github.com/org/skills.git@v1.0.0", "unsupported_url"),
        ("https://user:token@github.com/org/skills.git@v1.0.0", "unsupported_url"),
        ("https://github.com/org/skills.git@--upload-pack=touch /tmp/x", "unsupported_version"),
        ("https://github.com/org/skills.git@../../etc", "unsupported_version"),
        ("", "missing_source"),
    ],
)
def test_an_address_is_checked_before_anything_is_fetched(source, rule, cache) -> None:
    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([source])

    assert refusal.value.rule == rule
    assert refusal.value.source == source


def test_a_repository_that_cannot_be_fetched_says_so(tmp_path, cache) -> None:
    with pytest.raises(SkillSourceRefused) as refusal:
        fetch_git_package(f"file://{tmp_path / 'nothing'}", "v1.0.0", tmp_path / "target")

    assert refusal.value.rule == "fetch_failed"


def test_a_source_larger_than_the_ceiling_is_refused(tmp_path, cache) -> None:
    package = _package(tmp_path / "authored")
    (package / "prompts").mkdir(parents=True, exist_ok=True)
    (package / "prompts" / "huge.md").write_text("x" * (5 * 1024 * 1024 + 1), encoding="utf-8")
    archive = _zip_of(package, tmp_path / "proposal.zip")

    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([archive])

    assert refusal.value.rule == "package_too_large"


def test_the_planning_module_takes_addresses_and_paths_in_one_parameter(tmp_path, cache) -> None:
    from unittest.mock import patch

    from agentic_sdk.modules import NextStepWithSkills

    url = _repository(tmp_path / "remote", _package(tmp_path / "authored", "meeting-notes", "minutes"), "v1.2.0")
    local = _package(tmp_path / "local", "proposal")

    with patch("agentic_sdk.llm.openai_compatible.OpenAI"):
        plan = NextStepWithSkills(
            api_key="test-key",
            base_url="https://example.openai.test/v1",
            model="foundry-openai-like",
            skill_packages=[f"{url}@v1.2.0", local],
        )

    assert [package.name for package in plan.packages] == ["meeting-notes", "proposal"]
