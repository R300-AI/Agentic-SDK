from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


MAPPING_FILE_NAME = "package.yaml"
"""The one file in a package that records which skill uses which instructions and prompts."""

WITHHELD_FROM_PLANNING_KEY = "disable-model-invocation"
"""The mapping declaration that keeps a skill out of the planning module's own choosing.

The key is the name Claude Code uses for the same thing. It lives in the mapping
file rather than in SKILL.md so that SKILL.md keeps only the fields the Agent
Skills standard defines, and a skill written for another tool loads unchanged.
"""

MAX_DESCRIPTION_CHARACTERS = 1024
"""The open skill format's limit on a description, which a planning module reads for every skill."""

DEFAULT_MAX_SKILL_CHARACTERS = 20_000
"""How much text one skill may add to a conversation, counting its body, instructions and prompts.

A skill taken up stays in the conversation until it ends, so it costs its size on
every later turn. This default is a placeholder: the limit is meant to follow the
context length of the models an agent is bound to, and that has not been set.
"""


class SkillPackageRefused(ValueError):
    """A package that cannot be mounted, and the one rule and file that says why."""

    def __init__(self, *, rule: str, path: str, package: str, detail: str) -> None:
        self.rule = rule
        self.path = path
        self.package = package
        self.detail = detail
        super().__init__(f"skill package {package!r} refused ({rule}) at {path}: {detail}")


@dataclass(frozen=True)
class Skill:
    """A named procedure for one kind of task, as a conversation receives it."""

    name: str
    description: str
    body: str
    instructions: tuple[str, ...]
    prompts: tuple[str, ...]
    package: str
    withheld_from_planning: bool = False

    def sections(self) -> list[str]:
        """What a conversation that takes up this skill carries: body, then instructions, then prompts.

        Instructions and prompts keep the order the mapping file lists them in.
        """
        return [part for part in (self.body, *self.instructions, *self.prompts) if part.strip()]


@dataclass(frozen=True)
class SkillPackage:
    """A self-contained set of skills and the instructions and prompts they use."""

    name: str
    path: Path
    maintainer: dict[str, str]
    skills: tuple[Skill, ...]

    @classmethod
    def load(cls, path: str | Path, *, max_skill_characters: int = DEFAULT_MAX_SKILL_CHARACTERS) -> "SkillPackage":
        """Read a package, refusing it on the first rule it breaks.

        Every refusal names one rule and one file, including the ones a broken
        mapping file causes: whoever mounts a package has to be told what to fix,
        and a parser error naming a line number is not that.

        Files no skill names are left alone — a package cloned from a repository
        carries a README, and refusing it for that stopped nothing the text-only
        rule does not already stop. See ADR-0004 and ADR-0006.
        """
        root = Path(path)
        name = root.name

        def refuse(rule: str, relative: str, detail: str) -> SkillPackageRefused:
            return SkillPackageRefused(rule=rule, path=relative, package=name, detail=detail)

        on_disk = sorted(root.rglob("*"))
        for candidate in on_disk:
            # A link passes as the text it points at, so a published package
            # could otherwise hand the model any file on the machine mounting it.
            if candidate.is_symlink():
                raise refuse("linked_file", _relative(root, candidate), "a skill package holds its own files, not links to other files")
        for file in (candidate for candidate in on_disk if candidate.is_file()):
            if not _is_text(file.read_bytes()):
                raise refuse("not_text", _relative(root, file), "a skill package holds text only")
        if not (root / MAPPING_FILE_NAME).is_file():
            raise refuse("missing_file", MAPPING_FILE_NAME, "a skill package needs a mapping file")

        try:
            loaded = yaml.safe_load((root / MAPPING_FILE_NAME).read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise refuse("invalid_mapping", MAPPING_FILE_NAME, f"the mapping file is not valid YAML: {error.__class__.__name__}") from error
        if not isinstance(loaded, dict):
            raise refuse("invalid_mapping", MAPPING_FILE_NAME, "the mapping file holds a name for the maintainer and one for the skills")
        entries = loaded.get("skills") or {}
        if not isinstance(entries, dict):
            raise refuse("invalid_mapping", MAPPING_FILE_NAME, "skills is written as one entry per skill name, not as a list")

        skills_dir = root / "skills"
        for directory in sorted(child.name for child in skills_dir.iterdir() if child.is_dir()) if skills_dir.is_dir() else []:
            if directory not in entries:
                raise refuse("name_mismatch", f"skills/{directory}/SKILL.md", "the mapping file has no entry for this skill")

        skills: list[Skill] = []
        for skill_name, raw_entry in entries.items():
            skill_name = str(skill_name)
            skill_file = f"skills/{skill_name}/SKILL.md"
            if raw_entry is not None and not isinstance(raw_entry, dict):
                raise refuse("invalid_mapping", MAPPING_FILE_NAME, f"the entry for skill {skill_name!r} lists which files it uses, not a single value")
            entry: dict[str, Any] = raw_entry or {}
            if _leaves_its_folder(skill_name):
                raise refuse("outside_package", skill_file, "a skill name is one directory under skills/")
            if not (root / skill_file).is_file():
                raise refuse("missing_file", skill_file, "the mapping file lists a skill that has no SKILL.md")
            for folder in ("instructions", "prompts"):
                named = entry.get(folder)
                if named is not None and not isinstance(named, list):
                    raise refuse("invalid_mapping", MAPPING_FILE_NAME, f"skill {skill_name!r} lists its {folder} as a list of file names")
                for file_name in named or []:
                    referenced = f"{folder}/{file_name}"
                    if _leaves_its_folder(str(file_name)):
                        raise refuse("outside_package", referenced, f"skill {skill_name!r} names a file outside {folder}/")
                    if not (root / referenced).is_file():
                        raise refuse("missing_file", referenced, f"skill {skill_name!r} uses a file the package does not have")
            withheld = entry.get(WITHHELD_FROM_PLANNING_KEY, False)
            if not isinstance(withheld, bool):
                raise refuse(
                    "invalid_declaration",
                    MAPPING_FILE_NAME,
                    f"skill {skill_name!r} declares {WITHHELD_FROM_PLANNING_KEY} as {withheld!r}; write true or false",
                )
            frontmatter, body = _split_frontmatter((root / skill_file).read_text(encoding="utf-8"))
            declared_name = str(frontmatter.get("name", "")).strip()
            description = str(frontmatter.get("description", "")).strip()
            # The name and description are recorded in SKILL.md and nowhere else
            # (ADR-0004). Reading the directory name instead mounted a skill with
            # an empty description and left the name check unable to fail.
            if not declared_name or not description:
                raise refuse("missing_frontmatter", skill_file, "SKILL.md needs a name and a description in its frontmatter")
            if declared_name != skill_name:
                raise refuse(
                    "name_mismatch",
                    skill_file,
                    f"SKILL.md names the skill {declared_name!r}, but its directory and mapping entry say {skill_name!r}",
                )
            if len(description) > MAX_DESCRIPTION_CHARACTERS:
                raise refuse(
                    "description_too_long",
                    skill_file,
                    f"the description has {len(description)} characters; the limit is {MAX_DESCRIPTION_CHARACTERS}",
                )
            skill = Skill(
                name=declared_name,
                description=description,
                body=body.strip(),
                instructions=tuple(_read_text(root / "instructions" / str(file)) for file in entry.get("instructions") or []),
                prompts=tuple(_read_text(root / "prompts" / str(file)) for file in entry.get("prompts") or []),
                package=name,
                withheld_from_planning=withheld,
            )
            size = sum(len(section) for section in skill.sections())
            if size > max_skill_characters:
                raise refuse(
                    "too_large",
                    skill_file,
                    f"the skill adds {size} characters to a conversation; the limit is {max_skill_characters}",
                )
            skills.append(skill)

        maintainer = {str(key): str(value) for key, value in (loaded.get("maintainer") or {}).items()}
        return cls(name=name, path=root, maintainer=maintainer, skills=tuple(skills))


def mount_packages(
    packages: Iterable[str | Path],
    *,
    max_skill_characters: int = DEFAULT_MAX_SKILL_CHARACTERS,
) -> tuple[SkillPackage, ...]:
    """Mount packages on one planning module, where every skill name must be unique.

    A package bringing a name another package already brought is refused, and the
    refusal names the package that got there first.
    """
    mounted: list[SkillPackage] = []
    owners: dict[str, str] = {}
    for candidate in packages:
        package = SkillPackage.load(candidate, max_skill_characters=max_skill_characters)
        for skill in package.skills:
            if skill.name in owners:
                raise SkillPackageRefused(
                    rule="name_taken",
                    path=f"skills/{skill.name}/SKILL.md",
                    package=package.name,
                    detail=f"skill {skill.name!r} is already brought by package {owners[skill.name]!r}",
                )
            owners[skill.name] = package.name
        mounted.append(package)
    return tuple(mounted)


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _leaves_its_folder(relative: str) -> bool:
    """Whether a name the mapping file gives would be read from outside its folder.

    A package never refers to another package's files, and a mapping file is
    written by whoever published the package, so a name that climbs out is
    refused before anything is opened.
    """
    path = PurePosixPath(relative)
    return not relative or "\\" in relative or path.is_absolute() or ".." in path.parts


def _relative(root: Path, file: Path) -> str:
    return file.relative_to(root).as_posix()


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    closing = text.find("\n---", 3)
    if closing == -1:
        return {}, text
    try:
        loaded = yaml.safe_load(text[3:closing])
    except yaml.YAMLError:
        loaded = None
    body = text[closing + len("\n---"):]
    return (loaded if isinstance(loaded, dict) else {}), body


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()
