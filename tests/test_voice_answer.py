from __future__ import annotations

import json
from unittest.mock import patch

from agentic_sdk import Workflow
from agentic_sdk.audio import FakeAudioOutput
from agentic_sdk.modules import PassThroughPerceive, PassThroughRetrieve, VoiceAnswerAction

from support import FoundryOpenAILikeClient


SPOKEN = "這款比較適合久站，兩千三百八，門市有現貨。"
DISPLAYED = "科技鞋墊 多功能型 / SKU 7037730 / NT$2,380 / 現貨 4 雙"


def voice_action(speech: FakeAudioOutput, action_text: str) -> VoiceAnswerAction:
    action = VoiceAnswerAction(
        api_key="k", base_url="https://example.test/v1", model="m", speech=speech
    )
    action._client = FoundryOpenAILikeClient(action_text=action_text)
    return action


def two_channel_reply() -> str:
    return json.dumps({"spoken": SPOKEN, "displayed": DISPLAYED}, ensure_ascii=False)


def _state_with_cancel(token):
    """A state the way the workflow hands one to a module mid-run."""
    from agentic_sdk.core import WorkflowState

    state = WorkflowState(workflow_name="voice", user_message="保固多久？")
    state.cancel = token
    return state


def run_with(action) -> object:
    workflow = Workflow(
        workflow_name="voice",
        perceive=PassThroughPerceive(),
        retrieve=PassThroughRetrieve(),
        action=action,
    )
    return workflow.run("有什麼鞋墊？")


def test_the_screen_and_the_voice_carry_different_things():
    """Reading the displayed content aloud is the failure this exists to avoid."""
    speech = FakeAudioOutput()

    result = run_with(voice_action(speech, two_channel_reply()))

    assert result.final_message == DISPLAYED
    assert speech.spoken == [SPOKEN]


def test_an_answer_with_nothing_particular_to_say_is_read_out():
    """No spoken channel is a plain answer, not a broken one."""
    speech = FakeAudioOutput()

    result = run_with(voice_action(speech, "保固十二個月。"))

    assert result.final_message == "保固十二個月。"
    assert speech.spoken == ["保固十二個月。"]


def test_speaking_starts_before_the_whole_answer_is_written():
    """Waiting for the displayed half would put a pause in front of every reply.

    Driven from the reply cut off part way through: the spoken field is
    complete, the JSON around it is not. Anything that waited for the whole
    answer to parse would say nothing at all here.
    """
    speech = FakeAudioOutput()
    truncated = '{"spoken": "' + SPOKEN + '", "displayed": "科技鞋墊'

    run_with(voice_action(speech, truncated))

    assert speech.spoken == [SPOKEN]


def test_interrupting_stops_the_synthesis_too():
    """Finishing a sentence nobody will hear costs money and says nothing."""
    from agentic_sdk.core.cancellation import CancellationToken

    speech = FakeAudioOutput()
    action = voice_action(speech, two_channel_reply())
    token = CancellationToken()

    class InterruptDuringPlayback:
        """Stands in for a person talking over the first moment of the reply."""

        def speak(self, text):
            speech.spoken.append(text)
            token.cancel("interjection")
            yield b"first"
            speech.abandoned.append(text)

    action._speech = InterruptDuringPlayback()
    workflow = Workflow(
        workflow_name="voice",
        perceive=PassThroughPerceive(),
        retrieve=PassThroughRetrieve(),
        action=action,
    )

    workflow.run("有什麼鞋墊？", cancel=token)

    assert speech.spoken == [SPOKEN]
    assert speech.abandoned == [], "synthesis kept going after the interruption"


def test_nothing_heard_is_reported_when_playback_never_started():
    """Interrupted before a sound came out: there is nothing to carry forward."""
    from agentic_sdk.core.cancellation import CancellationToken

    speech = FakeAudioOutput()
    action = voice_action(speech, two_channel_reply())
    token = CancellationToken()
    token.cancel("interjection")

    workflow = Workflow(
        workflow_name="voice",
        perceive=PassThroughPerceive(),
        retrieve=PassThroughRetrieve(),
        action=action,
    )
    result = workflow.run("有什麼鞋墊？", cancel=token)

    assert result.interrupt_payload.get("heard", "") == ""


def test_only_what_was_played_is_reported_as_heard():
    """The producer of the heard text, not a hand-fed value.

    Speech lags generation, so an answer cut off mid-playback has a tail that
    was written and never spoken. Reporting the whole thing would let the next
    turn refer back to a sentence nobody heard.
    """
    from agentic_sdk.core.cancellation import CancellationToken

    token = CancellationToken()
    action = voice_action(FakeAudioOutput(), "")
    state = _state_with_cancel(token)

    token.cancel("interjection", heard_seconds=2.0)
    action._speak("保固期是十二個月，延長保固可以再加兩年，另外配件另計", state)

    assert state.delivered_so_far == "保固期是十二個月"


def test_an_answer_nobody_interrupted_is_reported_whole():
    from agentic_sdk.core.cancellation import CancellationToken

    token = CancellationToken()
    action = voice_action(FakeAudioOutput(), "")
    state = _state_with_cancel(token)

    action._speak("保固十二個月", state)

    assert state.delivered_so_far == "保固十二個月"


def test_a_reply_that_ignores_the_contract_is_still_readable():
    """Models answer in their own JSON sometimes, and a person then sees braces.

    Live against gpt-5.4 the reply to 「一加一等於多少？」 came back as
    {"问题": "1 + 1", "答案": 2} — neither field the contract asks for. The raw
    object went on the screen and was read out loud, brackets and quotes and
    all. It gets flattened into lines instead: nothing is invented, and nothing
    that was answered is thrown away.
    """
    from agentic_sdk.modules.action.voice_answer import _split_channels

    spoken, displayed = _split_channels('{"问题": "1 + 1", "答案": 2}')

    assert displayed == "问题：1 + 1\n答案：2"
    assert spoken == displayed


def test_an_answer_that_is_not_json_is_left_alone():
    from agentic_sdk.modules.action.voice_answer import _split_channels

    assert _split_channels("保固十二個月。") == ("保固十二個月。", "保固十二個月。")


def test_a_speaking_module_will_not_invent_its_own_source():
    import pytest

    with pytest.raises(TypeError):
        VoiceAnswerAction(api_key="k", base_url="https://example.test/v1", model="m")


def test_a_displayed_half_written_as_an_object_still_reads_as_text():
    """A model that answers the screen half with a structure must not put braces on the screen."""
    from agentic_sdk.modules.action.voice_answer import _split_channels

    spoken, displayed = _split_channels(json.dumps({
        "spoken": "這週六晚上還有場。",
        "displayed": {"價格": {"費率": "尖峰", "每小時": "NT$400"}, "常見訂法": ["兩小時 NT$800"]},
    }, ensure_ascii=False))

    assert spoken == "這週六晚上還有場。"
    assert "{" not in displayed and "'" not in displayed
    assert "價格" in displayed and "NT$400" in displayed and "兩小時 NT$800" in displayed


def test_a_spoken_half_written_as_a_list_is_still_said_as_a_sentence():
    from agentic_sdk.modules.action.voice_answer import _split_channels

    spoken, _ = _split_channels(json.dumps({"spoken": ["還有場", "要幫你留嗎"], "displayed": "A 場 20:00–22:00"}, ensure_ascii=False))

    assert "[" not in spoken and "'" not in spoken
    assert "還有場" in spoken and "要幫你留嗎" in spoken
