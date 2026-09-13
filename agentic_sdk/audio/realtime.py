"""A live transcription session, on the OpenAI SDK's realtime client.

Kept apart from the module that uses it so the module can be driven by a fake,
and so the protocol details — which are the fiddly part — live in one place.

One of those details cost an afternoon and is guarded by the defaults below:
an utterance is only transcribed once the service hears silence after it. Audio
that stops dead never finishes, and looks exactly like a hung connection. A
caller that gates on loudness must let the quiet tail through, which is what
the speech gate's hangover is for.

This talks to OpenAI and to nothing else. An endpoint that opens its
connections differently is reached by subclassing and overriding ``_open`` —
everything after the connection is the same standard protocol, so a subclass
writes one method and inherits the rest. Accepting somebody else's client here
instead would read as an integration with whatever they passed, which is a
promise this project does not make. See ADR-0003.
"""

from __future__ import annotations

import base64
import threading
from typing import Any, Callable, Mapping


DEFAULT_TURN_DETECTION = {
    "type": "server_vad",
    "threshold": 0.5,
    "silence_duration_ms": 300,
}
"""Let the service decide where an utterance ends.

Server-side voice activity is what makes an interjection possible: it reports
someone starting to speak about 600ms in, while the words take nearly four
seconds. A caller that waited for the words would still be talking over them.
"""


class RealtimeTranscription:
    """Streams microphone audio to a transcription model and reports back."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        language: str = "zh",
        prompt: str = "",
        turn_detection: Mapping[str, Any] | None = None,
        connect_timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._language = language
        # A language code says which language, never which script: "zh" comes
        # back simplified whoever is speaking. The prompt is where a caller
        # says which Chinese its people actually write.
        self._prompt = prompt.strip()
        self._turn_detection = dict(turn_detection or DEFAULT_TURN_DETECTION)

        self._speech_started: list[Callable[[], None]] = []
        self._transcript: list[Callable[[str], None]] = []
        self._connection: Any = None
        self._sending = threading.Lock()
        self._ready = threading.Event()
        self._closing = False
        self._failure: BaseException | None = None

        # The connection is a context manager that has to stay open, and its
        # recv blocks — so it lives in a thread of its own, and the caller's
        # thread only ever writes.
        self._thread = threading.Thread(target=self._run, name="realtime-transcription", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=connect_timeout):
            raise TimeoutError("speech service did not accept the connection in time")
        if self._failure is not None:
            raise self._failure

    def _open(self) -> Any:
        """Open a live transcription connection, and nothing else.

        The one method a different endpoint has to replace. Everything after
        this — the session settings, the audio frames, the events — is the same
        wherever the connection came from, so a subclass inherits all of it:

            class MyTranscription(RealtimeTranscription):
                def _open(self):
                    return SomeClient(...).beta.realtime.connect(model=self._model)
        """
        from openai import OpenAI

        return OpenAI(api_key=self._api_key, base_url=self._base_url).beta.realtime.connect(
            model=self._model,
            # What this connection is for, rather than a vendor's quirk: this
            # transport only ever opens transcription sessions.
            extra_query={"intent": "transcription"},
        )

    # ── AudioInputTransport ─────────────────────────────────────────────

    def send(self, pcm16: bytes) -> None:
        if self._connection is None or not pcm16:
            return
        with self._sending:
            self._connection.send(
                {
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm16).decode("ascii"),
                }
            )

    def on_speech_started(self, callback: Callable[[], None]) -> None:
        self._speech_started.append(callback)

    def on_transcript(self, callback: Callable[[str], None]) -> None:
        self._transcript.append(callback)

    def close(self) -> None:
        self._closing = True
        if self._connection is not None:
            self._connection.close()

    # ── the session ─────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            with self._open() as connection:
                self._connection = connection
                connection.send(
                    {
                        "type": "transcription_session.update",
                        "session": {
                            "input_audio_format": "pcm16",
                            "input_audio_transcription": {
                                "model": self._model,
                                "language": self._language,
                                **({"prompt": self._prompt} if self._prompt else {}),
                            },
                            "turn_detection": self._turn_detection,
                        },
                    }
                )
                self._ready.set()
                self._listen(connection)
        except BaseException as error:  # noqa: BLE001 - reported to the constructor
            self._failure = error
            self._ready.set()

    def _listen(self, connection: Any) -> None:
        while not self._closing:
            try:
                event = connection.recv()
            except (StopIteration, StopAsyncIteration):
                return
            except Exception:  # noqa: BLE001 - a closed socket ends the session
                return
            kind = str(_field(event, "type") or "")
            if kind == "input_audio_buffer.speech_started":
                _fan_out(self._speech_started)
            elif kind.endswith("transcription.completed"):
                text = str(_field(event, "transcript") or "").strip()
                if text:
                    _fan_out(self._transcript, text)


def _field(event: Any, name: str) -> Any:
    """Events arrive as parsed objects from the SDK and as plain dicts in tests."""
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _fan_out(callbacks: list, *args: Any) -> None:
    for callback in list(callbacks):
        callback(*args)
