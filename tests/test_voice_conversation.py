"""一次對話有很多輪，而接線每一次都一樣。

麥克風要一直餵、每一輪要換一個新的取消權杖、聽到完整一句才跑一輪——
這些每個語音應用都得寫，寫錯的後果又很重（沿用舊權杖會讓下一輪一開始就結束，
播放時停止收音會讓打斷失效）。所以它們屬於工作流程，不屬於使用它的人。
"""

from __future__ import annotations

import time

from agentic_sdk import Workflow
from agentic_sdk.audio import FakeAudioInput
from agentic_sdk.core import ModuleOutput
from agentic_sdk.modules import VoiceTextPerceive


class AnswersWithWhatItHeard:
    name = "action"

    def __init__(self) -> None:
        self.tokens: list[int] = []

    def __call__(self, state):
        self.tokens.append(id(state.cancel))
        return ModuleOutput(next_module=None, payload={"latest_final_message": state.latest_user_message()})


def quiet(count: int = 20, pause: float = 0.02):
    for _ in range(count):
        yield b"\x00" * 320
        time.sleep(pause)


def test_a_turn_for_每一句_and_a_fresh_token_each_time():
    audio = FakeAudioInput()
    action = AnswersWithWhatItHeard()
    workflow = Workflow(perceive=VoiceTextPerceive(transport=audio), action=action)

    def microphone():
        audio.transcribe("這週六還有場地嗎")
        yield from quiet()
        audio.transcribe("那費率呢")
        yield from quiet()

    results = list(workflow.converse(audio=microphone(), tail_seconds=0.3))

    assert [result.final_message for result in results] == ["這週六還有場地嗎", "那費率呢"]
    assert len(set(action.tokens)) == 2, "兩輪共用了同一個取消權杖，第二輪一開始就會被當成已取消"


def test_it_keeps_listening_while_it_is_answering():
    """播放期間停止收音，就等於關掉打斷。"""
    audio = FakeAudioInput()
    heard_during_the_answer: list[int] = []

    class TakesAMoment:
        name = "action"

        def __call__(self, state):
            time.sleep(0.4)
            heard_during_the_answer.append(len(audio.sent))
            return ModuleOutput(next_module=None, payload={"latest_final_message": "好"})

    workflow = Workflow(perceive=VoiceTextPerceive(transport=audio), action=TakesAMoment())

    def microphone():
        audio.transcribe("問題")
        for _ in range(40):
            yield b"\x7f\x7f" * 160  # 夠大聲，閘門會放行
            time.sleep(0.02)

    before = len(audio.sent)
    list(workflow.converse(audio=microphone(), tail_seconds=0.3))

    assert heard_during_the_answer and heard_during_the_answer[0] > before, "回答期間沒有繼續收音"


def test_it_ends_when_the_microphone_ends():
    """一段錄音放完就該收工，而不是永遠等下去。"""
    audio = FakeAudioInput()
    workflow = Workflow(perceive=VoiceTextPerceive(transport=audio), action=AnswersWithWhatItHeard())

    def microphone():
        audio.transcribe("只有這一句")
        yield from quiet(count=5)

    results = list(workflow.converse(audio=microphone()))

    assert len(results) == 1
