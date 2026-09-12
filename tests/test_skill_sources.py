"""Where a skill package comes from — ADR-0007.

Observed through ``mount_packages`` and the planning module that takes the
sources: what a source resolves to, and what it is refused for.
"""

from __future__ import annotations

import os
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
    return work.as_uri()


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


def test_an_archive_resolves_to_the_same_directory_every_time(tmp_path, cache) -> None:
    """A package mounted once must mount again from the cache, not from a wrapper around it."""
    archive = _zip_of(_package(tmp_path / "authored"), tmp_path / "proposal.zip")
    first = mount_packages([archive])

    second = mount_packages([archive])

    assert [package.name for package in second] == [package.name for package in first] == ["proposal"]
    assert [skill.name for skill in second[0].skills] == ["write"]


def test_a_refused_archive_names_the_archive_the_caller_gave(tmp_path, cache) -> None:
    package = _package(tmp_path / "authored")
    (package / "prompts").mkdir(parents=True, exist_ok=True)
    (package / "prompts" / "huge.md").write_text("x" * (5 * 1024 * 1024 + 1), encoding="utf-8")
    archive = _zip_of(package, tmp_path / "proposal.zip")

    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([archive])

    assert refusal.value.source == str(archive)


def test_a_fetch_that_failed_leaves_nothing_to_mount(tmp_path, cache) -> None:
    with pytest.raises(SkillSourceRefused):
        mount_packages([f"file://{tmp_path / 'nothing'}@v1.0.0"])

    assert not any(path.is_dir() for path in cache.rglob("nothing"))


@pytest.mark.parametrize(
    "source",
    [
        "https:///org/skills.git@v1.0.0",
        "https://github.com@v1.0.0",
        "https://github.com/org/skills.git@v1@v2",
    ],
)
def test_an_address_that_names_no_repository_is_refused(source, cache) -> None:
    """An address is a host, a repository and one version — not two of any of them."""
    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([source])

    assert refusal.value.rule == "unsupported_url"


def test_a_repository_over_the_ceiling_is_refused(tmp_path, cache) -> None:
    package = _package(tmp_path / "authored", "meeting-notes")
    (package / "prompts").mkdir(parents=True, exist_ok=True)
    (package / "prompts" / "huge.md").write_text("x" * (5 * 1024 * 1024 + 1), encoding="utf-8")
    url = _repository(tmp_path / "remote", package, "v1.0.0")

    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([f"{url}@v1.0.0"])

    assert refusal.value.rule == "package_too_large"


def test_a_repository_is_fetched_without_the_machines_own_git_settings(tmp_path, cache, monkeypatch) -> None:
    """A login stored for another purpose is never offered to a skill package's repository."""
    seen: dict = {}
    url = _repository(tmp_path / "remote", _package(tmp_path / "authored", "meeting-notes"), "v1.0.0")
    original = subprocess.run

    def remember(command, **kwargs):
        # Building the repository above used git too; only the fetch passes an
        # environment, and that is the one this test is about.
        if kwargs.get("env"):
            seen.setdefault("environment", kwargs["env"])
            seen.setdefault("commands", []).append(command)
        return original(command, **kwargs)

    monkeypatch.setattr("agentic_sdk.skills.source.subprocess.run", remember)

    mount_packages([f"{url}@v1.0.0"])

    assert seen["environment"]["GIT_TERMINAL_PROMPT"] == "0"
    assert seen["environment"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert seen["environment"]["GIT_CONFIG_GLOBAL"] == os.devnull
    assert ["git", "-c", "credential.helper=", "fetch", "--depth", "1", "--quiet", "origin", "v1.0.0"] in seen["commands"]
    # The history is how the files arrived, not part of the package.
    assert not any(path.name == ".git" for path in cache.rglob("*"))


def test_an_archive_of_loose_files_is_the_package_itself(tmp_path, cache) -> None:
    package = _package(tmp_path / "authored")
    archive = tmp_path / "meeting-notes.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as written:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                written.write(file, file.relative_to(package).as_posix())

    mounted = mount_packages([archive])

    assert [package.name for package in mounted] == ["meeting-notes"]


def test_an_archive_that_writes_outside_itself_is_refused(tmp_path, cache) -> None:
    archive = tmp_path / "escaping.zip"
    with zipfile.ZipFile(archive, "w") as written:
        written.writestr("../escaped.md", "不該落在技能包外面")

    with pytest.raises(SkillSourceRefused) as refusal:
        mount_packages([archive])

    assert refusal.value.rule == "unreadable_archive"
    assert not (tmp_path / "escaped.md").exists()


def test_without_a_setting_packages_are_kept_in_the_users_cache(monkeypatch) -> None:
    from agentic_sdk.skills.source import cache_root

    monkeypatch.delenv("AGENTIC_SDK_SKILL_PACKAGES", raising=False)

    assert cache_root() == Path.home() / ".cache" / "agentic-sdk" / "skill-packages"
