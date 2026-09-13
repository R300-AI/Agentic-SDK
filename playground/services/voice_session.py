"""Finding a running answer from outside the request that started it.

The person speaking and the workflow answering are on different connections:
one is a websocket carrying audio, the other an HTTP request streaming a reply.
The interjection arrives on the first and has to stop something running on the
second, so the two need a name in common.

They share a process, which is what makes this a dictionary rather than
infrastructure — and why the Playground refuses to start with more than one
worker. Across processes the interjection would land somewhere the workflow
is not, and nothing would report it.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable, Iterator

from agentic_sdk.audio.realtime import RealtimeTranscription
from agentic_sdk.audio.speech import SpeechOutput
from agentic_sdk.core.cancellation import CancellationToken

if TYPE_CHECKING:  # imported lazily below — see listen()
    from agentic_sdk.audio.transport import AudioInputTransport
    from agentic_sdk.modules.perceive.voice_text import VoiceTextPerceive


class VoiceSessionRegistry:
    """Which answer belongs to which listening session."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._listeners: dict[str, "VoiceTextPerceive"] = {}
        self._speakers: dict[str, Callable[[str], None]] = {}
        self._lock = threading.Lock()

    def attach_speaker(self, session_id: str, speaker: Callable[[str], None]) -> None:
        """Register how this session gets audio to whoever is listening."""
        with self._lock:
            self._speakers[str(session_id)] = speaker

    def say(self, session_id: str, text: str) -> bool:
        """Start playing this out now. False if nobody is listening any more.

        Called the moment the spoken half of an answer is written, while the
        displayed half is still being generated — the pause before a reply is
        what makes an agent feel like a form rather than a conversation.
        """
        with self._lock:
            speaker = self._speakers.get(str(session_id))
        if speaker is None:
            return False
        speaker(text)
        return True

    def listen(self, session_id: str, transport: "AudioInputTransport") -> "VoiceTextPerceive":
        """Give this session somewhere to send its microphone.

        The listening module rather than the raw transport, because the gate in
        front of it is the thing standing between a quiet room and a stream of
        words nobody said.

        The import is here rather than at the top of the file because a
        websocket arriving while the runner is still warming its modules
        deadlocked the two threads on Python's import lock, and the agent
        never finished starting.
        """
        from agentic_sdk.modules.perceive.voice_text import VoiceTextPerceive

        listener = VoiceTextPerceive(transport=transport)
        with self._lock:
            self._listeners[str(session_id)] = listener
        return listener

    def listener(self, session_id: str) -> "VoiceTextPerceive | None":
        with self._lock:
            return self._listeners.get(str(session_id))

    def open(self, session_id: str) -> CancellationToken:
        """Start a session, replacing any answer still running under that name.

        A reload opens the same session again. Leaving the first one registered
        would strand an answer nobody can reach and nobody is listening to.
        """
        token = CancellationToken()
        with self._lock:
            self._tokens[str(session_id)] = token
        return token

    def interject(self, session_id: str, *, heard_seconds: float | None) -> bool:
        """Stop this session's answer. False if there is nothing to stop.

        ``heard_seconds`` is how long the person actually listened, which only
        whatever is playing the audio knows: speech lags generation, so it is
        not how much was written. ``None`` when the interruption was noticed
        somewhere that cannot know — the transcription service hears someone
        begin, but has never played a note. Unknown has to stay unknown:
        reporting nought there would erase an answer the person did hear.
        """
        with self._lock:
            token = self._tokens.get(str(session_id))
        if token is None:
            return False
        token.cancel(
            "interjection",
            heard_seconds=None if heard_seconds is None else float(heard_seconds),
        )
        return True

    def close(self, session_id: str) -> None:
        with self._lock:
            self._tokens.pop(str(session_id), None)
            listener = self._listeners.pop(str(session_id), None)
            self._speakers.pop(str(session_id), None)
        if listener is not None:
            # The transcription session bills for as long as it is open, and
            # nobody is on the other end of this one any more.
            listener.close()

    def token(self, session_id: str) -> CancellationToken | None:
        with self._lock:
            return self._tokens.get(str(session_id))


class SessionSpeech:
    """The action module's speaker, when the speaker is in a browser.

    Handing the words to the page as soon as they exist is the whole point: it
    synthesises and plays them while the rest of the answer is still being
    written. Nothing comes back through here, because the audio never passes
    through the module — which is why yielding nothing is the honest answer
    rather than an omission.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self.reached_someone = False

    def speak(self, text: str) -> Iterator[bytes]:
        # A page that closed mid-answer is not a failure. The run finishes,
        # and there is simply nobody left to hear the rest of it — recorded
        # rather than dropped, because "nobody heard this" is the difference
        # between a quiet answer and a broken one.
        self.reached_someone = registry.say(self._session_id, text)
        return iter(())


def open_transcription() -> "AudioInputTransport | None":
    """Start a transcription session on the configured endpoint, if there is one.

    Returns nothing when no speech endpoint is configured, so the page can say
    so — an agent that silently never hears anything looks like a broken
    microphone, and the person spends the next minute talking louder.
    """
    from playground.services.key_vault_config import key_vault_settings

    endpoint = next(
        (item for item in key_vault_settings().speech_endpoints if item.id == "transcribe"),
        None,
    )
    if endpoint is None:
        return None
    if _test_mode():
        # The test key vault holds an endpoint that does not exist. Opening a
        # transcription session against it would fail on connect, which would
        # make the whole socket untestable — including from a browser, which
        # is the only place the microphone half can be exercised at all.
        from agentic_sdk.audio import FakeAudioInput

        return FakeAudioInput()
    return AzureRealtimeTranscription(endpoint=endpoint, prompt=TRADITIONAL_CHINESE_PROMPT)


TRADITIONAL_CHINESE_PROMPT = "請以臺灣慣用的繁體中文輸出，例如「這週六」「兩小時」「時段」「確認」。"
"""What to write, not what language: without it every utterance comes back simplified.

The people using this Playground write Traditional Chinese, and the language
code has no way to say so — ``zh`` is the only value the service takes.
"""


def _test_mode() -> bool:
    from playground.services.key_vault_config import _test_mode_enabled

    return _test_mode_enabled()


def open_synthesis():
    """Start a synthesis session on the configured endpoint, if there is one."""
    from playground.services.key_vault_config import key_vault_settings

    endpoint = next(
        (item for item in key_vault_settings().speech_endpoints if item.id == "tts"),
        None,
    )
    if endpoint is None:
        return None
    if _test_mode():
        from agentic_sdk.audio import FakeAudioOutput

        return FakeAudioOutput()
    return AzureSpeechOutput(endpoint=endpoint)


AZURE_REALTIME_API_VERSION = "2025-04-01-preview"
"""The preview this deployment speaks. A vendor's calendar, not the SDK's."""


AZURE_SPEECH_API_VERSION = "2025-03-01-preview"
"""What the synthesis deployment answers to."""


def _azure_client(endpoint, api_version: str):
    """The OpenAI SDK's own Azure client, built from what the key vault holds.

    The key vault holds the endpoints this Playground offers, in whatever shape
    they arrive — a complete operation URL here, a resource root elsewhere.
    Turning that into a client is this layer's job and always will be: the
    stored settings are not required to be OpenAI-shaped, and requiring it
    would make the Playground's own configuration answer to the SDK.
    """
    from openai import AzureOpenAI

    root = str(endpoint.endpoint).split("/openai/")[0].rstrip("/")
    return AzureOpenAI(azure_endpoint=root, api_key=endpoint.api_key, api_version=api_version)


class AzureRealtimeTranscription(RealtimeTranscription):
    """This Playground's own endpoint, reached the way that endpoint wants.

    The SDK talks to OpenAI and to nothing else; choosing Azure is a decision
    this layer made, so this class lives here rather than there. Only opening
    the connection differs — the session settings, the audio frames and the
    events are all inherited. See ADR-0003.
    """

    def __init__(self, *, endpoint, **rest) -> None:
        self._endpoint = endpoint
        super().__init__(model=endpoint.deployment_name, **rest)

    def _open(self):
        return _azure_client(self._endpoint, AZURE_REALTIME_API_VERSION).beta.realtime.connect(
            model=self._model,
            # Not optional here: without it the socket opens and then answers
            # every message with an error.
            extra_query={"intent": "transcription"},
        )


class AzureSpeechOutput(SpeechOutput):
    """The speaking half of the same decision."""

    def __init__(self, *, endpoint, **rest) -> None:
        self._endpoint = endpoint
        super().__init__(model=endpoint.deployment_name, **rest)

    def _open_stream(self, text: str):
        client = _azure_client(self._endpoint, AZURE_SPEECH_API_VERSION)
        return client.audio.speech.with_streaming_response.create(
            model=self._model, voice=self._voice, input=text,
            response_format=self._response_format,
        )


def speech_unavailable_message() -> str:
    return "這個 Playground 還沒有設定語音服務，所以聽不到你說話。你可以改用打字的。"


def unknown_session_message() -> str:
    return "這個語音會話已經結束了。重新整理頁面就會開始新的一個。"


registry = VoiceSessionRegistry()
"""The one every request shares, for the same reason they share a process."""
