from __future__ import annotations

from agentic_sdk import Workflow
from agentic_sdk.audio import FakeAudioInput
from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput
from agentic_sdk.core.cancellation import CancellationToken, WorkflowInterrupted
from agentic_sdk.modules import PassThroughRetrieve, VoiceTextPerceive


HEARD = "保固期限是十二個月"
UNHEARD = "，另外還有延長保固方案可以加購。"


class AnswerCutOffPartWayThrough:
    """Produces a whole answer, of which only the beginning was spoken aloud."""

    name = "action"

    def __init__(self, audio: FakeAudioInput) -> None:
        self._audio = audio

    def __call__(self, state):
        state.report_delivered(HEARD)
        self._audio.start_speaking()
        state.cancel.raise_if_cancelled()
        raise AssertionError("should have been interrupted")


def voice_workflow(audio: FakeAudioInput) -> Workflow:
    return Workflow(
        workflow_name="voice",
        perceive=VoiceTextPerceive(transport=audio),
        retrieve=PassThroughRetrieve(),
        action=AnswerCutOffPartWayThrough(audio),
    )


def test_the_interruption_reports_what_was_heard_not_what_was_written():
    """Speech lags generation, so the tail was written and never spoken.

    Keeping it would let the next turn refer back to a sentence nobody heard.
    """
    audio = FakeAudioInput()
    workflow = voice_workflow(audio)

    audio.transcribe("保固多久？")
    result = workflow.run(cancel=CancellationToken())

    assert result.interrupt_payload["delivered"] == HEARD
    assert UNHEARD not in str(result.interrupt_payload)


def test_only_what_was_heard_survives_in_the_conversation():
    audio = FakeAudioInput()
    workflow = voice_workflow(audio)

    audio.transcribe("保固多久？")
    workflow.run(cancel=CancellationToken())

    assistant_turns = [turn.content for turn in workflow.memory.turns if turn.role == "assistant"]
    assert assistant_turns == [HEARD]
    assert all(UNHEARD not in turn for turn in assistant_turns)


def test_the_next_turn_is_told_it_was_cut_off():
    """Without being told, the agent answered 「沒有足夠資料指出前一段停在哪」."""
    audio = FakeAudioInput()
    workflow = voice_workflow(audio)

    audio.transcribe("保固多久？")
    workflow.run(cancel=CancellationToken())

    interrupted_turn = [turn for turn in workflow.memory.turns if turn.metadata.get("interrupted")]
    assert interrupted_turn, "nothing in the conversation says the turn was cut off"
    assert interrupted_turn[-1].content == HEARD


def test_an_answer_nobody_heard_leaves_nothing_behind():
    """Interrupted before a word was spoken: there is nothing to carry on from."""
    audio = FakeAudioInput()

    class SilentAction:
        name = "action"

        def __call__(self, state):
            audio.start_speaking()
            state.cancel.raise_if_cancelled()
            raise AssertionError("should have been interrupted")

    workflow = Workflow(
        workflow_name="voice",
        perceive=VoiceTextPerceive(transport=audio),
        retrieve=PassThroughRetrieve(),
        action=SilentAction(),
    )

    audio.transcribe("保固多久？")
    result = workflow.run(cancel=CancellationToken())

    assert result.interrupt_payload.get("heard", "") == ""
    assert [turn.content for turn in workflow.memory.turns if turn.role == "assistant"] == []


def test_the_model_is_told_it_was_cut_off_and_what_was_heard():
    """Being told is the difference between carrying on and starting again."""
    from agentic_sdk.memory import InContextMemory
    from agentic_sdk.modules.action.generative import _build_messages
    from agentic_sdk.core import WorkflowState

    memory = InContextMemory(workflow_name="w")
    memory.append_message("user", "保固多久？")
    memory.append_message("assistant", HEARD, metadata={"source": "workflow.run", "interrupted": True})
    memory.append_message("user", "那延長保固呢？")
    state = WorkflowState(workflow_name="w", user_message="那延長保固呢？", memory=memory)

    prompt = " ".join(str(message.get("content", "")) for message in _build_messages(state, None))

    assert HEARD in prompt
    assert "打斷" in prompt
    assert "不要從頭重述" in prompt


def test_only_the_part_that_was_played_is_remembered():
    """Speech lags generation: the tail was written but never reached anyone.

    Remembering it whole makes the agent's next answer refer back to something
    the person never heard, which reads as the agent inventing the exchange.
    """
    from agentic_sdk.audio.speech_rate import heard_portion

    spoken = "保固期是十二個月，延長保固可以再加兩年，另外配件另計"

    assert heard_portion(spoken, 2.0) == "保固期是十二個月"


def test_an_interruption_that_reports_no_timing_keeps_what_was_said():
    """The SDK path has no player, so nothing knows the duration."""
    from agentic_sdk.audio.speech_rate import heard_portion

    assert heard_portion("保固十二個月", None) == "保固十二個月"


def test_hearing_the_whole_answer_is_not_trimmed_by_rounding():
    from agentic_sdk.audio.speech_rate import heard_portion

    assert heard_portion("保固十二個月", 30.0) == "保固十二個月"


def test_only_what_was_heard_survives_when_the_page_does_the_playing():
    """The audio never passes through the module, and the trim has to happen anyway.

    In a browser the page plays the spoken half, so the module's transport
    yields nothing and hands the text over in an instant; the person talks over
    it seconds later, while the module is long finished. Measured live, someone
    who heard 2.4 seconds had all 144 characters written into the conversation
    as if they had heard every word.
    """
    import json

    from agentic_sdk.audio.transport import PlayedElsewhere
    from agentic_sdk.modules import PassThroughPerceive, VoiceAnswerAction

    from support import FoundryOpenAILikeClient

    spoken = "這週六尖峰每面每小時四百元，週日也是尖峰價，平日白天兩百五，C 場整天停用。"
    token = CancellationToken()

    class PageThatGetsTalkedOver(PlayedElsewhere):
        """Hands the words to the page, which reports being talked over 2s in."""

        def speak(self, text):
            pieces = super().speak(text)
            token.cancel("interjection", heard_seconds=2.0)
            return pieces

    action = VoiceAnswerAction(
        api_key="k", base_url="https://example.test/v1", model="m", speech=PageThatGetsTalkedOver()
    )
    action._client = FoundryOpenAILikeClient(
        action_text=json.dumps({"spoken": spoken, "displayed": spoken}, ensure_ascii=False)
    )
    workflow = Workflow(
        workflow_name="voice",
        perceive=PassThroughPerceive(),
        retrieve=PassThroughRetrieve(),
        action=action,
    )

    workflow.run("這週六多少錢？", cancel=token)

    assistant_turns = [t.content for t in workflow.memory.turns if t.role == "assistant"]
    assert assistant_turns, "被打斷的那一輪什麼都沒留下"
    heard = assistant_turns[-1]
    assert spoken.startswith(heard), f"留下的不是說出口的開頭：{heard}"
    assert len(heard) <= 12, f"兩秒只講得完約九個字，卻留下 {len(heard)} 字：{heard}"


def test_the_stream_noticing_the_stop_does_not_erase_what_the_person_reported():
    """Two accounts of one interruption, and only one of them was there.

    A stream that sees the stop flag reports how much it had produced. The
    person reports how long they had been listening. The second is the only one
    that says what reached them, so it is the one that has to survive.
    """
    audio = FakeAudioInput()
    token = CancellationToken()

    class StreamThatNoticesTheStop:
        name = "action"

        def __call__(self, state):
            state.report_delivered(HEARD + UNHEARD)
            audio.start_speaking()
            token.cancel("interjection", heard_seconds=2.0)
            raise WorkflowInterrupted("cancelled", {"produced_characters": 51})

    workflow = Workflow(
        workflow_name="voice",
        perceive=VoiceTextPerceive(transport=audio),
        retrieve=PassThroughRetrieve(),
        action=StreamThatNoticesTheStop(),
    )

    audio.transcribe("保固多久？")
    result = workflow.run(cancel=token)

    assert result.interrupt_payload["heard_seconds"] == 2.0
    assert result.interrupt_payload["reason"] == "interjection"
    assert result.interrupt_payload["produced_characters"] == 51
