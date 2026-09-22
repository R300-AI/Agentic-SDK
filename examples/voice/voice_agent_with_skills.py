"""語音進、語音出，而且帶技能包的 Agent——不經過 Playground。

Playground 畫面上看得到的東西都在 SDK 裡；Playground 多做的是 SDK 刻意不碰的
兩端：把麥克風收進來、把聲音放出去。這支範例把那兩端各寫成一個小類別，也就是
你換成真實音效裝置時要動的地方。

技能包由規劃模組掛載（ADR-0006）：工作流程本身不知道技能這回事，其他模組也
不用改。來源可以是資料夾、zip、或帶版本的儲存庫位址（ADR-0007）：

    examples/skills/front-desk
    /path/to/front-desk.zip
    https://github.com/org/front-desk.git@v1.0.0

用一段錄好的 WAV 當麥克風，所以沒有麥克風也跑得起來：

    .venv/bin/python examples/voice/voice_agent_with_skills.py question.wav
    .venv/bin/python examples/voice/voice_agent_with_skills.py question.wav https://github.com/org/front-desk.git@v1.0.0

WAV 必須是 16 位元單聲道，取樣率不拘：會重取樣成轉寫服務要的 16 kHz。

需要的環境變數：

    CHAT_API_KEY / CHAT_BASE_URL / CHAT_MODEL            規劃與回答
    TRANSCRIBE_API_KEY / TRANSCRIBE_BASE_URL / TRANSCRIBE_MODEL   聽
    TTS_API_KEY / TTS_BASE_URL / TTS_MODEL               說
"""

from __future__ import annotations

import array
import os
import sys
import time
import wave
from pathlib import Path
from typing import Iterator

from agentic_sdk import Workflow
from agentic_sdk.audio.realtime import RealtimeTranscription
from agentic_sdk.audio.speech import SpeechOutput
from agentic_sdk.core.cancellation import CancellationToken
from agentic_sdk.modules import (
    SKILL_TURN_METADATA_KEY,
    NextStepWithSkills,
    VoiceAnswerAction,
    VoiceTextPerceive,
)


SERVICE_RATE = 16000
CHUNK_SAMPLES = 1600  # 十分之一秒
DEFAULT_SKILLS = Path(__file__).resolve().parents[1] / "skills" / "front-desk"


class PlayThroughSpeaker:
    """會被聽見的合成，而不只是被產生出來。

    ``SpeechOutput`` 回傳音訊，沒有人播它——行動模組把串流抽乾後就把位元組丟掉，
    因為聲音從哪裡出來不是 SDK 的事。包一層才是：每一塊先交給播放的一方，再
    yield 出去，這樣被插話而中止串流時，聲音也會跟著停。
    """

    def __init__(self, voice: SpeechOutput, into: Path) -> None:
        self._voice = voice
        self._into = into

    def speak(self, text: str) -> Iterator[bytes]:
        played = bytearray()
        try:
            for piece in self._voice.speak(text):
                # 真實程式在這裡寫進音效裝置。寫成檔案是為了讓沒有喇叭的機器
                # 也跑得完這支範例。
                played.extend(piece)
                yield piece
        finally:
            with wave.open(str(self._into), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(24000)  # 合成服務回傳的取樣率
                out.writeframes(bytes(played))


def microphone_from(path: Path) -> Iterator[bytes]:
    """把 WAV 當成麥克風讀，並轉成轉寫服務要的取樣率。"""
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise SystemExit("需要 16 位元單聲道 WAV")
        rate = source.getframerate()
        samples = array.array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    step = rate / SERVICE_RATE
    resampled = array.array("h", (samples[int(index * step)] for index in range(int(len(samples) / step))))
    for start in range(0, len(resampled), CHUNK_SAMPLES):
        yield resampled[start : start + CHUNK_SAMPLES].tobytes()


def build(skills: str | Path) -> tuple[Workflow, VoiceTextPerceive, Path]:
    """把四個模組接起來，並把技能包掛在規劃模組上。"""
    spoken_to = Path("spoken-answer.wav")

    # 音訊來源在外面建好再交進去。模組自己沒有建立音訊來源的能力，這是「多接
    # 一家廠商不等於改程式碼」的原因（ADR-0003）。
    listening = RealtimeTranscription(
        api_key=os.environ["TRANSCRIBE_API_KEY"],
        base_url=os.environ.get("TRANSCRIBE_BASE_URL") or None,
        model=os.environ["TRANSCRIBE_MODEL"],
    )
    speaking = SpeechOutput(
        api_key=os.environ["TTS_API_KEY"],
        base_url=os.environ.get("TTS_BASE_URL") or None,
        model=os.environ["TTS_MODEL"],
    )
    endpoint = {
        "api_key": os.environ["CHAT_API_KEY"],
        "base_url": os.environ["CHAT_BASE_URL"],
        "model": os.environ["CHAT_MODEL"],
    }

    perceive = VoiceTextPerceive(transport=listening)
    # 技能只在這一行出現。規劃模組會把可挑選的技能列給模型，使用者也可以用
    # /booking 直接指名；被選中的技能，本文、instructions、prompts 會原封不動
    # 成為對話裡的一個回合。
    plan = NextStepWithSkills(skill_packages=skills, **endpoint)
    action = VoiceAnswerAction(speech=PlayThroughSpeaker(speaking, spoken_to), **endpoint)

    workflow = Workflow(
        workflow_name="語音櫃檯",
        perceive=perceive,
        plan=plan,
        action=action,
    )
    return workflow, perceive, spoken_to


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    heard_from = Path(sys.argv[1])
    skills = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SKILLS

    workflow, perceive, spoken_to = build(skills)
    plan = workflow.modules["plan"]
    print("掛上的技能：", ", ".join(f"{skill.name}（{skill.package}）" for skill in plan.skills) or "（沒有）")

    print("正在聽…")
    for chunk in microphone_from(heard_from):
        perceive.hear(chunk)  # 安靜的片段不會離開這台機器
        time.sleep(CHUNK_SAMPLES / SERVICE_RATE)  # 麥克風是即時到達的

    # 服務靠聽到靜默來判斷一句話結束，所以文字會在說完之後才到。
    waited = 0.0
    while not perceive.pending_input() and waited < 10:
        time.sleep(0.2)
        waited += 0.2
    if not perceive.pending_input():
        print("沒有聽到任何話。")
        return 1
    print(f"聽到：{perceive.pending_input()}")

    # 這個 token 是「被插話」抵達一個已經在跑的執行的方式：感知模組握著它，
    # 偵測到有人開口就取消。
    result = workflow.run(cancel=CancellationToken())

    taken_up = [turn.metadata[SKILL_TURN_METADATA_KEY] for turn in result.memory.turns
                if (turn.metadata or {}).get(SKILL_TURN_METADATA_KEY)]
    print(f"這一輪用到的技能：{taken_up[-1] if taken_up else '（沒有）'}")
    print(f"畫面上顯示：{result.final_message}")
    print(f"說出口的：{spoken_to}（{spoken_to.stat().st_size} 位元組）")
    if result.stop_reason == "interrupted":
        # 被打斷時，留在對話裡的是對方真正聽到的那一段，不是整段產生出來的話。
        print(f"被打斷了，對方只聽到：{result.interrupt_payload.get('delivered', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
