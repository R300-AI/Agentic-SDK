"""The listening transport, on the SDK's realtime client rather than a hand-rolled one."""

from __future__ import annotations

import base64
import queue
import time
from types import SimpleNamespace

from agentic_sdk.audio.realtime import RealtimeTranscription


class _Connection:
    def __init__(self, incoming):
        self.sent = []
        self.closed = False
        self._incoming = incoming

    def send(self, event):
        self.sent.append(event)

    def recv(self):
        item = self._incoming.get()
        if item is None:
            raise StopIteration
        return item

    def close(self):
        self.closed = True


class _Manager:
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        return self._connection

    def __exit__(self, *_exc):
        return False


class _Elsewhere(RealtimeTranscription):
    """An endpoint reached some other way — the one method a subclass replaces.

    This is exactly what a caller writes for an endpoint the SDK knows nothing
    about, so the test drives the same seam they would.
    """

    def __init__(self, **kwargs):
        self.incoming = queue.Queue()
        self.connection = _Connection(self.incoming)
        self.opened = False
        super().__init__(**kwargs)

    def _open(self):
        self.opened = True
        return _Manager(self.connection)


def open_session(**kwargs):
    session = _Elsewhere(model="transcribe-1", **kwargs)
    return session, session


def settle():
    time.sleep(0.05)


def test_an_endpoint_reached_some_other_way_replaces_one_method():
    """Everything after the connection is the same, so a subclass inherits it.

    The transport talks to OpenAI and to nothing else. Taking somebody else's
    client instead would read as an integration with whatever was passed, which
    is a promise this project does not make.
    """
    client, session = open_session()

    assert client.opened is True
    # The protocol came with the base class: the subclass wrote no part of it.
    assert client.connection.sent[0]["type"] == "transcription_session.update"
    session.close()


def test_the_shipped_transport_talks_to_openai_and_says_so():
    """No client argument, no vendor parameters: there is nothing to point elsewhere."""
    import inspect

    accepted = set(inspect.signature(RealtimeTranscription.__init__).parameters)

    assert "client" not in accepted
    assert "extra_query" not in accepted
    assert "extra_headers" not in accepted


def test_it_asks_the_service_to_decide_where_an_utterance_ends():
    """Server-side voice activity is what makes an interruption possible at all."""
    client, session = open_session()

    opening = client.connection.sent[0]
    assert opening["type"] == "transcription_session.update"
    assert opening["session"]["input_audio_format"] == "pcm16"
    assert opening["session"]["turn_detection"]["type"] == "server_vad"
    session.close()


def test_audio_goes_out_as_the_protocol_wants_it():
    client, session = open_session()

    session.send(b"\x01\x02\x03\x04")
    settle()

    appended = [event for event in client.connection.sent if event["type"] == "input_audio_buffer.append"]
    assert base64.b64decode(appended[-1]["audio"]) == b"\x01\x02\x03\x04"
    session.close()


def test_someone_starting_to_speak_is_reported_before_any_words():
    client, session = open_session()
    began = []
    session.on_speech_started(lambda: began.append(True))

    client.incoming.put({"type": "input_audio_buffer.speech_started"})
    settle()

    assert began == [True]
    session.close()


def test_a_finished_utterance_is_reported():
    client, session = open_session()
    heard = []
    session.on_transcript(heard.append)

    client.incoming.put(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "保固多久？"}
    )
    settle()

    assert heard == ["保固多久？"]
    session.close()


def test_it_can_be_told_which_chinese_to_write():
    """「zh」 alone comes back simplified; a Taiwanese desk needs the other one."""
    client, session = open_session(prompt="請以臺灣繁體中文輸出，例如「這週六」「兩小時」。")
    settle()

    opening = client.connection.sent[0]

    assert opening["session"]["input_audio_transcription"]["prompt"] == "請以臺灣繁體中文輸出，例如「這週六」「兩小時」。"
    session.close()


def test_nothing_extra_is_sent_when_there_is_nothing_to_say():
    client, session = open_session()
    settle()

    opening = client.connection.sent[0]

    assert "prompt" not in opening["session"]["input_audio_transcription"]
    session.close()
