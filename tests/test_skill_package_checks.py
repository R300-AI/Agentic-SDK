"""What a skill package must look like to be mounted — ADR-0004, amended by ADR-0006.

Observed through the mounting function: hand it a directory, and it either
returns the skills it holds or refuses the package, naming one rule and one file.
"""

from __future__ import annotations

import shutil

import pytest

from agentic_sdk.skills import SkillPackageRefused, mount_packages

from support import write_skill_package


def _write_skill(**overrides) -> dict:
    return {"write": {"description": "把計畫書的一章寫出來", "body": "先確認章節目標。", **overrides}}


def _skills_of(*packages, **kwargs):
    return [skill for package in mount_packages(list(packages), **kwargs) for skill in package.skills]


def _refusal(*packages, **kwargs) -> SkillPackageRefused:
    with pytest.raises(SkillPackageRefused) as caught:
        mount_packages(list(packages), **kwargs)
    return caught.value


def test_a_package_hands_over_its_skills_in_the_order_the_mapping_gives(tmp_path) -> None:
    package = write_skill_package(
        tmp_path,
        skills=_write_skill(instructions=["steps.md"], prompts=["format.md"]),
        instructions={"steps.md": "列出三個重點。"},
        prompts={"format.md": "# 標題"},
    )

    skills = _skills_of(package)

    assert [skill.name for skill in skills] == ["write"]
    assert skills[0].description == "把計畫書的一章寫出來"
    assert skills[0].sections() == ["先確認章節目標。", "列出三個重點。", "# 標題"]
    assert skills[0].package == "proposal"


def test_a_package_carrying_something_other_than_text_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(), extra_files={"prompts/logo.png": b"\x89PNG\r\n\x1a\n\x00\x00"})

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("not_text", "prompts/logo.png")


def test_a_mapping_that_names_a_file_the_package_lacks_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(instructions=["missing.md"]))

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("missing_file", "instructions/missing.md")


def test_a_file_no_skill_uses_is_mounted_all_the_same(tmp_path) -> None:
    """A package cloned from a repository carries a README, and that is fine.

    The rule this replaces refused the whole package for it. What it was meant
    to stop — smuggling material nobody reads — the text-only rule and the size
    caps already stop.
    """
    package = write_skill_package(
        tmp_path,
        skills=_write_skill(instructions=["first.md"]),
        instructions={"first.md": "列出三個重點。", "leftover.md": "沒人用的流程。"},
        extra_files={"README.md": "這個技能包的說明\n", "LICENSE": "Apache-2.0\n"},
    )

    assert [skill.name for skill in _skills_of(package)] == ["write"]


def test_a_skill_can_be_withheld_from_the_planning_modules_own_choosing(tmp_path) -> None:
    package = write_skill_package(
        tmp_path,
        skills={
            "write": {"description": "把計畫書的一章寫出來", "body": "先確認章節目標。"},
            "submit": {"description": "送出申請並通知窗口", "body": "先確認收件人。", "keep_from_the_agent": True},
        },
    )

    kept = {skill.name: skill.keep_from_the_agent for skill in _skills_of(package)}

    assert kept == {"write": False, "submit": True}


def test_a_declaration_that_is_not_true_or_false_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(keep_from_the_agent="有時候"))

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("invalid_declaration", "package.yaml")


def test_a_skill_whose_name_disagrees_with_its_directory_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(frontmatter_name="draft"))

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("name_mismatch", "skills/write/SKILL.md")


def test_a_skill_directory_the_mapping_does_not_list_is_refused(tmp_path) -> None:
    package = write_skill_package(
        tmp_path,
        skills=_write_skill(),
        mapping={"maintainer": {"name": "王小明", "contact": "ming@example.test"}, "skills": {}},
    )

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("name_mismatch", "skills/write/SKILL.md")


def test_a_second_package_bringing_a_name_already_taken_is_refused_and_names_the_first(tmp_path) -> None:
    first = write_skill_package(tmp_path, "proposal", skills=_write_skill())
    second = write_skill_package(tmp_path, "marketing", skills=_write_skill())

    refusal = _refusal(first, second)

    assert (refusal.rule, refusal.path) == ("name_taken", "skills/write/SKILL.md")
    assert refusal.package == "marketing"
    assert "proposal" in str(refusal)


def test_a_description_longer_than_1024_characters_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(description="字" * 1025))

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("description_too_long", "skills/write/SKILL.md")


def test_a_description_of_exactly_1024_characters_is_mounted(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(description="字" * 1024))

    assert [skill.name for skill in _skills_of(package)] == ["write"]


def test_a_skill_whose_content_exceeds_the_limit_is_refused(tmp_path) -> None:
    package = write_skill_package(
        tmp_path,
        skills=_write_skill(body="字" * 30, prompts=["format.md"]),
        prompts={"format.md": "格" * 30},
    )

    refusal = _refusal(package, max_skill_characters=50)

    assert (refusal.rule, refusal.path) == ("too_large", "skills/write/SKILL.md")


def test_a_package_without_a_mapping_file_is_refused(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill())
    (package / "package.yaml").unlink()

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("missing_file", "package.yaml")


def test_an_instruction_or_prompt_path_that_leaves_the_package_is_refused(tmp_path) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    (packages / "secret.txt").write_text("伺服器上的密碼", encoding="utf-8")
    package = write_skill_package(packages, skills=_write_skill(prompts=["../../secret.txt"]))

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("outside_package", "prompts/../../secret.txt")


def test_a_skill_name_that_leaves_the_skills_directory_is_refused(tmp_path) -> None:
    packages = tmp_path / "packages"
    (packages / "secret-skill").mkdir(parents=True)
    (packages / "secret-skill" / "SKILL.md").write_text("---\nname: secret-skill\ndescription: 外面的技能\n---\n伺服器上的內容\n", encoding="utf-8")
    package = write_skill_package(
        packages,
        skills=_write_skill(),
        mapping={"maintainer": {"name": "王小明", "contact": "ming@example.test"}, "skills": {"../../secret-skill": {}}},
    )
    shutil.rmtree(package / "skills")

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("outside_package", "skills/../../secret-skill/SKILL.md")


def test_a_file_that_links_to_somewhere_else_is_refused(tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("伺服器上的密碼", encoding="utf-8")
    package = write_skill_package(tmp_path / "packages", skills=_write_skill(prompts=["format.md"]), prompts={"format.md": "格式"})
    linked = package / "prompts" / "format.md"
    linked.unlink()
    linked.symlink_to(secret)

    refusal = _refusal(package)

    assert (refusal.rule, refusal.path) == ("linked_file", "prompts/format.md")


def test_the_maintainer_comes_back_with_the_package(tmp_path) -> None:
    package = write_skill_package(tmp_path, skills=_write_skill(), maintainer={"name": "陳怡君", "contact": "yijun@example.test"})

    mounted = mount_packages([package])

    assert mounted[0].name == "proposal"
    assert mounted[0].maintainer == {"name": "陳怡君", "contact": "yijun@example.test"}
