from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

from agentic_sdk.core import Attachment
from agentic_sdk.llm import OpenAIChatResponse


class FoundryOpenAILikeClient:
    def __init__(
        self,
        *,
        perceive_intent: str = "test_intent",
        perceive_summary: str = "測試用感知摘要。",
        perceive_details: dict | None = None,
        plan_sequence: list[str] | None = None,
        reflect_verdict: str = "pass",
        reflect_reason: str = "test reflect ok",
        reflect_suggestion: str = "",
        action_text: str = "mock action response",
        tool_calls: list[dict] | None = None,
        model_id: str = "foundry-openai-like",
    ) -> None:
        self._perceive_intent = perceive_intent
        self._perceive_summary = perceive_summary
        self._perceive_details = perceive_details
        self._plan_sequence = list(plan_sequence or ["retrieve", "action"])
        self._reflect_verdict = reflect_verdict
        self._reflect_reason = reflect_reason
        self._reflect_suggestion = reflect_suggestion
        self._action_text = action_text
        self._tool_calls = list(tool_calls or [])
        self._plan_index = 0
        self._model_id = model_id
        self.last_create_kwargs: dict | None = None
        self.chat = _FoundryChatNamespace(self)
        self.models = _FoundryModelNamespace(self)

    def _respond(self, *, system: str, user: str) -> OpenAIChatResponse:
        if system.startswith("PERCEIVE"):
            payload = {
                "intent": self._perceive_intent,
                "summary": self._perceive_summary,
            }
            if self._perceive_details is not None:
                payload["details"] = self._perceive_details
        elif system.startswith("PLAN"):
            next_module = self._plan_sequence[min(self._plan_index, len(self._plan_sequence) - 1)]
            self._plan_index += 1
            payload = {
                "thought": f"route to {next_module}",
                "next_module": next_module,
            }
        elif system.startswith("REFLECT"):
            payload = {
                "verdict": self._reflect_verdict,
                "reason": self._reflect_reason,
                "suggestion": self._reflect_suggestion,
            }
        else:
            return OpenAIChatResponse(
                content=self._action_text,
                model=self._model_id,
                input_tokens=max(1, len(user) // 4),
                output_tokens=max(1, len(self._action_text) // 4),
            )

        content = json.dumps(payload, ensure_ascii=False)
        return OpenAIChatResponse(
            content=content,
            model=self._model_id,
            input_tokens=max(1, len(user) // 4),
            output_tokens=max(1, len(content) // 4),
        )


class _FoundryChatNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self.completions = _FoundryCompletionsNamespace(owner)


class _FoundryCompletionsNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self._owner = owner

    def create(self, **kwargs):
        self._owner.last_create_kwargs = dict(kwargs)
        messages = kwargs.get("messages", [])
        system = next((str(message.get("content", "")) for message in messages if message.get("role") == "system"), "")
        user = next((str(message.get("content", "")) for message in messages if message.get("role") == "user"), "")
        response = self._owner._respond(system=system, user=user)
        model = kwargs.get("model", self._owner._model_id)

        if kwargs.get("stream"):
            chunks = [
                SimpleNamespace(
                    model=model,
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=char))],
                )
                for char in response.content
            ]
            for index, tool_call in enumerate(self._owner._tool_calls):
                function = tool_call.get("function") or {}
                chunks.append(
                    SimpleNamespace(
                        model=model,
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=index,
                                            id=tool_call.get("id"),
                                            type=tool_call.get("type"),
                                            function=SimpleNamespace(
                                                name=function.get("name"),
                                                arguments=function.get("arguments"),
                                            ),
                                        )
                                    ],
                                )
                            )
                        ],
                    )
                )
            return chunks

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response.content, tool_calls=self._owner._tool_calls))],
            usage=SimpleNamespace(
                prompt_tokens=response.input_tokens,
                completion_tokens=response.output_tokens,
            ),
            model=model,
        )


class _FoundryModelNamespace:
    def __init__(self, owner: FoundryOpenAILikeClient) -> None:
        self._owner = owner

    def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=self._owner._model_id)])


@dataclass
class StaticVisionQueryBuilder:
    rewritten_query: str

    def __call__(self, text: str, attachments: list[Attachment]) -> str:
        return self.rewritten_query if attachments else text


def build_source(*steps: tuple[str, object]) -> str:
    """Compile the Python source a Builder session exports after these answers.

    Each step is a ``(step_key, choice)`` pair, applied to the default spec in
    order, the same way the Builder applies a user's answers. With no steps this
    is the source for an untouched Builder session.

    Note that an untouched spec retrieves through ``PassThroughRetrieve``, while
    the compiled-source construction path this replaces defaulted to
    ``KeywordRetrieve()``. The two disagree; reconciling them is tracked
    separately.
    """
    # Imported inside the function so SDK-only tests importing this module do
    # not pull the playground package, and Flask with it, into their process.
    from playground.services.workflow_spec import apply_builder_step, compile_python_source, default_spec

    spec = default_spec()
    for step_key, choice in steps:
        spec = apply_builder_step(spec, step_key, choice)
    return compile_python_source(spec)


def build_spec(*steps: tuple[str, object]) -> dict:
    """Build the agent spec a Builder session holds after these answers.

    Each step is a ``(step_key, choice)`` pair, applied to the default spec in
    order. Use this wherever a test drives the execution tier, and
    :func:`build_source` where a test asserts on the exported Python text.

    Q4 is answered for you when the steps do not answer it, because an agent
    whose output format is unchosen is no longer runnable — the Builder used to
    fill that in silently, which is how an unfinished agent could reach the
    gallery. The stand-in is the answer that needs no model, so a test about
    gates or memory does not accidentally require a binding. Pass an
    ``output_format`` step to choose otherwise, or reach for
    :func:`~playground.services.workflow_spec.default_spec` to hold a spec with
    the question genuinely unanswered.
    """
    from playground.services.workflow_spec import apply_builder_step, default_spec

    spec = default_spec()
    if not any(step_key == "output_format" for step_key, _ in steps):
        spec = apply_builder_step(spec, "output_format", "direct")
    for step_key, choice in steps:
        spec = apply_builder_step(spec, step_key, choice)
    return spec


def write_skill_package(
    root,
    name: str = "proposal",
    *,
    skills: dict[str, dict],
    instructions: dict[str, str] | None = None,
    prompts: dict[str, str] | None = None,
    maintainer: dict[str, str] | None = None,
    mapping: dict | None = None,
    extra_files: dict[str, bytes | str] | None = None,
):
    """Write a skill package directory the way an author would lay one out.

    ``skills`` maps a skill directory name to ``description``, ``body``, and the
    ``instructions`` and ``prompts`` file names it uses, in order. Give
    ``frontmatter_name`` to write a ``SKILL.md`` whose name disagrees with its
    directory, and ``keep_from_the_agent`` to write the mapping declaration that
    withholds a skill from the planning module's own choosing. ``mapping``
    replaces the generated mapping file outright, and ``extra_files`` adds
    anything else, text or bytes, by relative path.
    """
    import yaml
    from pathlib import Path

    package = Path(root) / name
    for skill_name, skill in skills.items():
        skill_dir = package / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = {"name": skill.get("frontmatter_name", skill_name), "description": skill.get("description", "")}
        (skill_dir / "SKILL.md").write_text(
            f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True)}---\n\n{skill.get('body', '')}\n",
            encoding="utf-8",
        )
    for folder, files in (("instructions", instructions or {}), ("prompts", prompts or {})):
        for file_name, text in files.items():
            path = package / folder / file_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    generated_skills: dict[str, dict] = {}
    for skill_name, skill in skills.items():
        entry: dict = {
            "instructions": list(skill.get("instructions", [])),
            "prompts": list(skill.get("prompts", [])),
        }
        if "keep_from_the_agent" in skill:
            entry["disable-model-invocation"] = skill["keep_from_the_agent"]
        generated_skills[skill_name] = entry
    generated = {
        "maintainer": maintainer or {"name": "王小明", "contact": "ming@example.test"},
        "skills": generated_skills,
    }
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.yaml").write_text(yaml.safe_dump(mapping if mapping is not None else generated, allow_unicode=True), encoding="utf-8")
    for relative, content in (extra_files or {}).items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return package


# ── 語音測試共用的音訊 ───────────────────────────────────────────────

def pcm(*samples: int) -> bytes:
    """One channel of 16-bit audio, the format the transcription service takes."""
    import struct

    return struct.pack(f"<{len(samples)}h", *samples)


def silence(frames: int = 1600) -> bytes:
    return pcm(*([0] * frames))


def speech(frames: int = 1600, level: int = 8000) -> bytes:
    """Alternating, so the frames carry energy rather than a constant offset."""
    return pcm(*([level, -level] * (frames // 2)))
