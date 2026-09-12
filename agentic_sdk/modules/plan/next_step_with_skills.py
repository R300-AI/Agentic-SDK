from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from agentic_sdk.core import WorkflowState
from agentic_sdk.modules.plan.next_step import NextStepPlan
from agentic_sdk.skills import DEFAULT_MAX_SKILL_CHARACTERS, Skill, mount_packages


SKILL_TURN_METADATA_KEY = "skill"
"""Marks the conversation turn a skill was taken up in, by the skill's name."""

_PICK_INSTRUCTION = (
    "Besides thought and next_module, also return the field skill. "
    "available_skills lists skills as name: description. Set skill to the exact name of the one skill "
    "whose description matches what the user is asking for, or to an empty string when no description matches."
)


class NextStepWithSkills(NextStepPlan):
    """Plan the next step, and take up a skill when this turn calls for one.

    Skills belong to the planning module: the workflow knows nothing about them,
    and no other module changes. A skill is taken up either because the person
    named it at the start of their message — ``/minutes …`` — or because the
    model picked it from the listing by its description. Either way the skill's
    own text joins the conversation word for word, as a turn of its own in the
    person's role. Nothing summarises it, nothing rewrites what was said
    earlier, and nothing reads the package again on later turns: the
    conversation carries it. See ADR-0006.
    """

    def __init__(
        self,
        *,
        skill_packages: Iterable[str | Path] = (),
        max_skill_characters: int = DEFAULT_MAX_SKILL_CHARACTERS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.packages = mount_packages(list(skill_packages), max_skill_characters=max_skill_characters)
        self.skills = tuple(skill for package in self.packages for skill in package.skills)
        self._by_name = {skill.name: skill for skill in self.skills}

    def _system_prompt_for(self, options: dict[str, str | None]) -> str:
        prompt = super()._system_prompt_for(options)
        listing = self._listing()
        if not listing:
            return prompt
        return f"{prompt}\n{_PICK_INSTRUCTION}\navailable_skills:\n{listing}"

    def _listing(self) -> str:
        """The skills the model may pick, as name and description, one per line."""
        return "\n".join(f"{skill.name}: {skill.description}" for skill in self.skills if not skill.withheld_from_planning)

    def _after_decision(self, state: WorkflowState, parsed: dict) -> tuple[dict, dict]:
        skill = self._named_by_the_person(state) or self._picked_by_the_model(parsed)
        if skill is None or self._already_taken_up(state, skill.name):
            return {}, {}
        self._take_up(state, skill)
        return {"picked_skill": skill.name}, {SKILL_TURN_METADATA_KEY: skill.name}

    def _named_by_the_person(self, state: WorkflowState) -> Skill | None:
        """The skill the person put at the start of their message, if it is mounted.

        A message that opens with something else shaped like a path — /usr/local
        — names no mounted skill, so it stays ordinary text.
        """
        message = str(state.user_message or "").strip()
        if not message.startswith("/"):
            return None
        return self._by_name.get(message[1:].split(maxsplit=1)[0] if len(message) > 1 else "")

    def _picked_by_the_model(self, parsed: dict) -> Skill | None:
        # A name nobody mounted is not a skill, however confidently it was written.
        return self._by_name.get(str(parsed.get("skill") or "").strip())

    def _already_taken_up(self, state: WorkflowState, name: str) -> bool:
        if state.memory is None:
            return False
        return any((turn.metadata or {}).get(SKILL_TURN_METADATA_KEY) == name for turn in state.memory.turns)

    def _take_up(self, state: WorkflowState, skill: Skill) -> None:
        if state.memory is None:
            return
        state.memory.append_message(
            "user",
            "\n\n".join(skill.sections()),
            metadata={SKILL_TURN_METADATA_KEY: skill.name, "package": skill.package},
        )
