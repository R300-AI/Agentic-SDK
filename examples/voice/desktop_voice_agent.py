"""A voice agent outside the Playground: microphone in, spoken answer out.

Everything the Playground shows is in the SDK; what the Playground adds is the
two ends the SDK deliberately does not own — capturing the microphone and
playing the audio. Both are one small class here, and both are the seam where
you put a real sound device instead.

Run it against a WAV of someone speaking, so it works with no microphone:

    .venv/bin/python examples/voice/desktop_voice_agent.py question.wav

The WAV must be 16-bit mono. Any rate: it is resampled to the 16 kHz the
transcription service takes.
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
from agentic_sdk.modules import VoiceAnswerAction, VoiceTextPerceive


SERVICE_RATE = 16000
CHUNK_SAMPLES = 1600  # a tenth of a second


class PlayThroughSpeaker:
    """Synthesis that is heard, not just produced.

    ``SpeechOutput`` returns audio and nothing plays it — the action module
    drains the stream and drops the bytes, because where sound comes out is not
    the SDK's business. Wrapping it is: yield each piece *after* handing it to
    whatever plays, so abandoning the stream on an interjection stops the sound
    as well as the synthesis.

    A wrapper like this one is not a special case. Every audio source reaches a
    module the same way — constructed outside and handed in — so the SDK cannot
    tell this apart from the transports it ships.
    """

    def __init__(self, voice: SpeechOutput, into: Path) -> None:
        self._voice = voice
        self._into = into

    def speak(self, text: str) -> Iterator[bytes]:
        played = bytearray()
        try:
            for piece in self._voice.speak(text):
                # A real program writes to a sound device here. Writing to a
                # file keeps the example runnable on a machine with no speaker.
                played.extend(piece)
                yield piece
        finally:
            with wave.open(str(self._into), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(24000)  # what the synthesis returns
                out.writeframes(bytes(played))


def microphone_from(path: Path) -> Iterator[bytes]:
    """Read a WAV as if it were a microphone, at the rate the service takes."""
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


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    spoken_to = Path("spoken-answer.wav")

    # The three endpoint settings are the same shape on every module.
    # Audio sources are built here and handed in. The modules hold no way to
    # build one, which is what keeps a second vendor from meaning a code change.
    # An endpoint reached differently is a subclass of these, written here in
    # your own code — see the notebook's last section.
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

    perceive = VoiceTextPerceive(transport=listening)
    action = VoiceAnswerAction(
        api_key=os.environ["CHAT_API_KEY"],
        base_url=os.environ["CHAT_BASE_URL"],
        model=os.environ["CHAT_MODEL"],
        speech=PlayThroughSpeaker(speaking, spoken_to),
    )
    workflow = Workflow(workflow_name="桌面語音 Agent", perceive=perceive, action=action)

    print("正在聽…")
    for chunk in microphone_from(Path(sys.argv[1])):
        perceive.hear(chunk)  # quiet chunks never leave this machine
        time.sleep(CHUNK_SAMPLES / SERVICE_RATE)  # a microphone arrives in real time

    # The service ends an utterance by hearing silence, so the words arrive a
    # moment after the talking stops.
    waited = 0.0
    while not perceive.pending_input() and waited < 10:
        time.sleep(0.2)
        waited += 0.2
    if not perceive.pending_input():
        print("沒有聽到任何話。")
        return 1
    print(f"聽到：{perceive.pending_input()}")

    # The token is how being talked over reaches a run that is already going:
    # the perceive module holds it, and voice activity cancels it.
    result = workflow.run(cancel=CancellationToken())

    print(f"畫面上顯示：{result.final_message}")
    print(f"說出口的：{spoken_to} ({spoken_to.stat().st_size} bytes)")
    if result.stop_reason == "interrupted":
        print(f"被打斷了，對方只聽到：{result.interrupt_payload.get('heard', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
