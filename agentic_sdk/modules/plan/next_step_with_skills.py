from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from agentic_sdk.core import WorkflowState
from agentic_sdk.modules.plan.next_step import NextStepPlan
from agentic_sdk.skills import DEFAULT_MAX_SKILL_CHARACTERS, Skill, mount_packages


DEFAULT_MAX_LISTING_CHARACTERS = 8_000
"""How much of the model's input the whole skill listing may take."""

DEFAULT_MAX_LISTING_DESCRIPTION_CHARACTERS = 1_536
"""How much of the listing one skill's description may take."""

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
        max_listing_characters: int = DEFAULT_MAX_LISTING_CHARACTERS,
        max_listing_description_characters: int = DEFAULT_MAX_LISTING_DESCRIPTION_CHARACTERS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._max_listing_characters = max_listing_characters
        self._max_listing_description_characters = max_listing_description_characters
        self.packages = mount_packages(list(skill_packages), max_skill_characters=max_skill_characters)
        self.skills = tuple(skill for package in self.packages for skill in package.skills)
        self._by_name = {skill.name: skill for skill in self.skills}

    def _system_prompt_for(self, state: WorkflowState, options: dict[str, str | None]) -> str:
        prompt = super()._system_prompt_for(state, options)
        if self._named_by_the_person(state) is not None:
            # The person said which skill this turn uses. Asking the model to
            # pick one as well only invites it to disagree with them.
            return prompt
        listing, _ = self._listing(state)
        if not listing:
            return prompt
        return f"{prompt}\n{_PICK_INSTRUCTION}\navailable_skills:\n{listing}"

    def _listing(self, state: WorkflowState) -> tuple[str, int]:
        """The skills the model may pick, and how many did not fit.

        Name and description, one skill per line, within a character budget: an
        agent with many skills would otherwise spend the model's whole input on
        a catalogue. An over-long description is cut first, so the skills after
        it keep their place; only when a whole line no longer fits does the
        listing stop, and what it stopped at is counted. A skill left out of the
        listing is still taken up when the person names it.

        A skill the conversation already carries stays on the list, marked, so
        the model reads what it is working with instead of picking it again.
        """
        offered = [skill for skill in self.skills if not skill.withheld_from_planning]
        lines: list[str] = []
        used = 0
        for position, skill in enumerate(offered):
            mark = " [already taken up]" if self._already_taken_up(state, skill.name) else ""
            line = f"{skill.name}: {self._cut(skill.description)}{mark}"
            cost = len(line) + (1 if lines else 0)
            if used + cost > self._max_listing_characters:
                return "\n".join(lines), len(offered) - position
            lines.append(line)
            used += cost
        return "\n".join(lines), 0

    def _cut(self, description: str) -> str:
        if len(description) <= self._max_listing_description_characters:
            return description
        return description[: self._max_listing_description_characters - 1] + "…"

    def _after_decision(self, state: WorkflowState, parsed: dict) -> tuple[dict, dict]:
        _, left_out = self._listing(state)
        skill = self._named_by_the_person(state) or self._picked_by_the_model(parsed)
        if skill is None or self._already_taken_up(state, skill.name):
            return {}, {"skills_left_out": left_out}
        self._take_up(state, skill)
        return {"picked_skill": skill.name}, {SKILL_TURN_METADATA_KEY: skill.name, "skills_left_out": left_out}

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
