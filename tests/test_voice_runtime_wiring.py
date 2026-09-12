"""Choosing voice in the Builder has to produce an agent that actually speaks.

Tested at the two seams the spec names — `build_spec`/`spec_to_config` for the
Builder's answers, and `run_agent` for everything from a spec to behaviour —
because the failure this file exists to catch is precisely a spec that says
voice and a runtime that quietly does something else.
"""

from __future__ import annotations

from unittest.mock import patch

from agentic_sdk.audio import FakeAudioInput
from agentic_sdk.config.workflow_config import ModuleSpec, build_module
from agentic_sdk.modules.action.voice_answer import VoiceAnswerAction
from playground.services.runner_service import run_agent, spec_to_config
from playground.services.voice_session import registry
from support import FoundryOpenAILikeClient, build_spec


def voice_spec() -> dict:
    return build_spec(("input_type", "voice"), ("output_format", "voice"))


def test_the_spec_can_name_the_speaking_action():
    """Half a registration is what ticket 01 exists to catch."""
    from agentic_sdk.audio import FakeAudioOutput

    module = build_module(
        ModuleSpec(
            kind="voice_answer",
            params={
                "api_key": "k",
                "base_url": "https://models.test/openai/v1",
                "model": "gpt-5.4",
                # An object, because an audio source is not a setting — the
                # same way semantic retrieve takes an embedder.
                "speech": FakeAudioOutput(),
            },
        )
    )

    assert isinstance(module, VoiceAnswerAction)


def test_the_builder_answers_name_the_voice_modules():
    config = spec_to_config(voice_spec())

    assert config.perceive_module == "VoiceTextPerceive"
    assert config.action_module == "VoiceAnswerAction"


def test_a_voice_agent_answers_the_question_it_was_asked():
    """The whole path: a voice spec, run, and a reply that came out of it.

    The spec said this seam covers 「語音 spec 建得起來」. It did not, and a
    voice agent ran as a pass-through that could neither hear nor speak.
    """
    with patch(
        "agentic_sdk.llm.openai_compatible.OpenAI",
        side_effect=[FoundryOpenAILikeClient(action_text='{"spoken": "十二個月", "displayed": "保固 12 個月"}')],
    ):
        execution = run_agent(voice_spec(), message="保固多久？", endpoint_selections={"action": "gpt-54"})

    assert execution["status"] == "completed"
    assert execution["final_message"] == "保固 12 個月"
    # The half that is only ever said, never shown.
    assert execution["spoken"] == "十二個月"


def test_a_voice_agent_speaks_into_the_session_that_is_listening():
    """Speaking somewhere nobody is listening is the failure that has no symptom."""
    registry.listen("run-seam", FakeAudioInput())
    registry.open("run-seam")
    handed_over: list[str] = []
    registry.attach_speaker("run-seam", handed_over.append)

    with patch(
        "agentic_sdk.llm.openai_compatible.OpenAI",
        side_effect=[FoundryOpenAILikeClient(action_text='{"spoken": "十二個月", "displayed": "保固 12 個月"}')],
    ):
        run_agent(
            voice_spec(),
            message="保固多久？",
            endpoint_selections={"action": "gpt-54"},
            voice_session_id="run-seam",
        )

    assert handed_over == ["十二個月"]


def test_a_voice_agent_still_works_for_someone_typing():
    """No microphone open is not a broken agent — it is someone using the keyboard."""
    with patch(
        "agentic_sdk.llm.openai_compatible.OpenAI",
        side_effect=[FoundryOpenAILikeClient(action_text='{"spoken": "十二個月", "displayed": "保固 12 個月"}')],
    ):
        execution = run_agent(
            voice_spec(),
            message="我用打的問保固",
            endpoint_selections={"action": "gpt-54"},
            voice_session_id="",
        )

    assert execution["status"] == "completed"
    assert execution["final_message"] == "保固 12 個月"


def test_a_spec_naming_a_module_with_no_parameter_table_says_so():
    """The registry and the allowed-parameter table must name the same kinds.

    voice_text reached the registry without reaching the table, so a spec that
    named it died on a bare KeyError from a dict lookup instead of the
    ValueError this function raises for everything it does not recognise.
    """
    import pytest

    from agentic_sdk.config.workflow_config import _MODULE_CONFIG_PARAMS

    registry_kinds = {"direct_answer", "evidence_check", "generative", "keyword", "next_step",
                      "pass_through", "pass_through_plan", "pass_through_retrieve", "plan_check", "semantic",
                      "text", "text_image", "tool_call_action", "voice_answer", "voice_text"}

    assert registry_kinds - set(_MODULE_CONFIG_PARAMS) == set()
    with pytest.raises(ValueError):
        build_module(ModuleSpec(kind="something_nobody_registered"))
