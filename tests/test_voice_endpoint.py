from __future__ import annotations

import json

from starlette.testclient import TestClient

import pytest
from types import SimpleNamespace

from agentic_sdk.audio import FakeAudioInput
from playground.main import app
from playground.services import voice_session
from playground.services.voice_session import registry
from support import pcm, silence, speech








@pytest.fixture
def speaker(monkeypatch):
    """Stand in for the synthesis service, so playback needs no credential."""
    from agentic_sdk.audio import FakeAudioOutput

    voice = FakeAudioOutput()
    monkeypatch.setattr(voice_session, "open_synthesis", lambda: voice)
    return voice


@pytest.fixture
def microphone(monkeypatch):
    """Stand in for the transcription service the endpoint would otherwise open."""
    audio = FakeAudioInput()
    monkeypatch.setattr(voice_session, "open_transcription", lambda: audio)
    return audio


def test_the_browser_never_receives_a_credential():
    """The gallery is public. A key handed to the page is a key given away."""
    with TestClient(app).websocket_connect("/playground/voice/session-a") as socket:
        opened = socket.receive_json()

    assert opened["type"] == "session.opened"
    body = json.dumps(opened)
    assert "api_key" not in body and "api-key" not in body


def test_speaking_over_the_answer_reaches_the_running_workflow():
    """The audio arrives here; the answer it interrupts is on another request."""
    token = registry.open("session-b")
    with TestClient(app).websocket_connect("/playground/voice/session-b") as socket:
        socket.receive_json()
        socket.send_json({"type": "interject", "heard_seconds": 1.75})
        acknowledged = socket.receive_json()

    assert acknowledged["type"] == "interjected"
    assert token.cancelled is True
    assert token.payload["heard_seconds"] == 1.75


def test_interrupting_an_answer_that_already_finished_is_explained():
    with TestClient(app).websocket_connect("/playground/voice/session-c") as socket:
        socket.receive_json()
        socket.send_json({"type": "interject", "heard_seconds": 0.5})
        answer = socket.receive_json()

    assert answer["type"] == "nothing_to_interrupt"
    # Sent back so the page can correct the turn it already committed: the
    # answer finished before the person talked over the end of it, and only
    # the page knows how much of it was played.
    assert answer["heard_seconds"] == 0.5
    assert "已經結束" in answer["message"]


def test_leaving_the_page_forgets_the_session():
    registry.open("session-d")
    with TestClient(app).websocket_connect("/playground/voice/session-d") as socket:
        socket.receive_json()

    assert registry.token("session-d") is None


def test_a_run_registers_itself_so_it_can_be_stopped():
    """Without this the endpoint has a name but nothing answering to it."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "playground"))
    from playground.services import runner_service
    from support import build_spec, pcm, silence, speech

    spec = build_spec(("retrieve_policy", "keyword"), ("output_format", "direct"))
    spec = runner_service.apply_builder_step(spec, "retrieve", {"keyword_pairs": "保固 = 十二個月"}) \
        if hasattr(runner_service, "apply_builder_step") else spec

    runner_service.run_agent(spec, message="保固多久？", endpoint_selections={}, voice_session_id="session-e")

    assert registry.token("session-e") is not None


def test_the_microphone_reaches_the_transcription_service(microphone):
    with TestClient(app).websocket_connect("/playground/voice/session-f") as socket:
        socket.receive_json()
        socket.send_bytes(speech())

        assert socket.receive_json()["type"] == "listening"

    assert microphone.sent == [speech()]


def test_a_quiet_room_is_not_transcribed(microphone):
    """Silence bills like speech and comes back as words nobody said."""
    with TestClient(app).websocket_connect("/playground/voice/session-g") as socket:
        socket.receive_json()
        socket.send_bytes(silence())
        socket.send_json({"type": "close"})

    assert microphone.sent == []


def test_what_was_said_comes_back_to_the_page(microphone):
    with TestClient(app).websocket_connect("/playground/voice/session-h") as socket:
        socket.receive_json()
        socket.send_bytes(speech())
        socket.receive_json()
        microphone.transcribe("保固多久？")
        heard = socket.receive_json()

    assert heard == {"type": "transcript", "text": "保固多久？"}


def test_starting_to_speak_stops_the_answer_without_waiting_for_words(microphone):
    """Speech starts at ~600ms and a transcript lands near four seconds.

    Waiting for the words means talking over the person for three more.
    """
    token = registry.open("session-i")
    with TestClient(app).websocket_connect("/playground/voice/session-i") as socket:
        socket.receive_json()
        socket.send_bytes(speech())
        socket.receive_json()
        microphone.start_speaking()
        warned = socket.receive_json()

    assert warned["type"] == "speech_started"
    assert token.cancelled is True
    # Nothing here played the audio, so nothing here knows how much was heard.
    # Claiming nought was would delete an answer the person did hear.
    assert token.payload["heard_seconds"] is None


def test_a_page_without_a_speech_endpoint_is_told_so(monkeypatch):
    """Silence would be indistinguishable from a broken microphone."""
    monkeypatch.setattr(voice_session, "open_transcription", lambda: None)
    with TestClient(app).websocket_connect("/playground/voice/session-j") as socket:
        socket.receive_json()
        socket.send_bytes(speech())
        answer = socket.receive_json()

    assert answer["type"] == "unavailable"
    assert "語音" in answer["message"]


def test_the_answer_is_played_in_the_browser(speaker):
    """The key stays here; the audio goes there."""
    with TestClient(app).websocket_connect("/playground/voice/session-k") as socket:
        socket.receive_json()
        socket.send_json({"type": "speak", "text": "保固十二個月"})
        played = []
        while (frame := socket.receive()).get("bytes") is not None:
            played.append(frame["bytes"])
        finished = json.loads(frame["text"])

    assert speaker.spoken == ["保固十二個月"]
    assert played != [] and finished["type"] == "spoken"


def test_speaking_over_it_stops_the_synthesis_mid_sentence(speaker):
    """Not just the playback: the rest of the sentence is never synthesised."""
    token = registry.open("session-l")
    token.cancel("interjection", heard_seconds=0.4)
    with TestClient(app).websocket_connect("/playground/voice/session-l") as socket:
        socket.receive_json()
        socket.send_json({"type": "speak", "text": "保固十二個月"})
        stopped = socket.receive_json()

    assert stopped["type"] == "spoken"
    assert speaker.abandoned == ["保固十二個月"]


def test_a_page_without_a_speech_endpoint_cannot_speak_either(monkeypatch):
    monkeypatch.setattr(voice_session, "open_synthesis", lambda: None)
    with TestClient(app).websocket_connect("/playground/voice/session-m") as socket:
        socket.receive_json()
        socket.send_json({"type": "speak", "text": "保固十二個月"})

        assert socket.receive_json()["type"] == "unavailable"


def test_the_person_who_interrupted_is_not_shown_an_error():
    """They did it on purpose. An error for that is absurd."""
    from playground.services.runner_service import _execution_status, _interruption_note

    interrupted = SimpleNamespace(aborted=False, interrupted=True, abort_reason=None)
    hop_limit = SimpleNamespace(aborted=True, interrupted=False, abort_reason="hop limit")

    assert _execution_status(interrupted, handoff_reason="") == "interrupted"
    assert _execution_status(hop_limit, handoff_reason="") == "aborted"
    assert "插話" in _interruption_note(interrupted)
    assert _interruption_note(hop_limit) == ""


def test_the_answer_starts_playing_before_it_is_finished():
    """The pause before a reply is what makes an agent feel like a form.

    The spoken half is handed over the moment that field closes, while the
    displayed half is still being written — so the page is playing something
    without ever having asked for it. Waiting for the finished answer would
    put that pause in front of every reply.
    """
    from agentic_sdk.audio.transport import AudioOutputTransport
    from playground.services.voice_session import SessionSpeech, registry

    handed_over = []
    registry.attach_speaker("session-n", handed_over.append)

    # What the action module holds: a transport like any other, whose audio
    # happens to come out somewhere else entirely.
    transport: AudioOutputTransport = SessionSpeech("session-n")

    assert list(transport.speak("保固十二個月")) == []
    assert handed_over == ["保固十二個月"]


def test_speaking_into_a_session_that_has_gone_away_is_not_an_error():
    """The page can close mid-answer. The run finishes either way."""
    from playground.services.voice_session import SessionSpeech

    assert list(SessionSpeech("never-opened").speak("保固十二個月")) == []


def test_the_playground_keeps_only_what_the_page_played():
    """The browser is the only thing that knows how long the answer played.

    It finishes after the run does, so the correction arrives late — and it
    lands on the record the Playground owns, not on the SDK's memory protocol,
    which every future kind of memory has to be able to implement. See ADR-0002.
    """
    from types import SimpleNamespace

    from playground.services.runner_conversation import RunnerConversationState

    written = "保固期是十二個月，延長保固可以再加兩年，另外配件另計"
    interrupted = SimpleNamespace(
        final_message=written,
        interrupted=True,
        interrupt_payload={"delivered": written, "heard_seconds": 2.0},
        entities={},
        entries=[],
    )

    state = RunnerConversationState.start().update_from_result(interrupted)

    assert [turn.content for turn in state.turns] == ["保固期是十二個月"]


class _VoiceThatWaitsOnTheService:
    """Synthesis as it really arrives: each piece is a wait, not a value.

    The service streams audio as it produces it, so pulling the next piece
    blocks for as long as the service takes. A fake that returns instantly
    hides the failure this test exists to catch.
    """

    def speak(self, text: str):
        import time

        for index in range(4):
            time.sleep(0.6)
            yield f"{text}:{index}".encode("utf-8")


def test_the_microphone_is_read_while_the_answer_is_playing(monkeypatch, microphone):
    """Barge-in is the whole point: talking over the answer has to reach the endpoint now.

    Measured live against the deployment, someone speaking while the answer
    played waited 3.8 seconds to be heard; speaking into the same session with
    nothing playing was heard in 0.05.
    """
    monkeypatch.setattr(voice_session, "open_synthesis", lambda: _VoiceThatWaitsOnTheService())

    with TestClient(app).websocket_connect("/playground/voice/session-barge") as socket:
        socket.receive_json()
        registry.say("session-barge", "一段要唸很久的回答")

        while socket.receive().get("bytes") is None:
            pass
        socket.send_bytes(speech())
        frame = socket.receive()

    registry.close("session-barge")
    assert frame.get("text") is not None, "麥克風被晾在一邊，先送出了下一塊聲音"
    assert json.loads(frame["text"])["type"] == "listening"


def test_the_record_is_corrected_when_the_answer_was_cut_off_after_the_run():
    """Playback outlives the run, so most interruptions have no run to stop.

    The answer is produced in a few seconds and takes half a minute to say. By
    the time the person talks over it the run is long finished and the whole
    answer is already in the conversation — including the half nobody heard.
    """
    from playground.services.runner_conversation import RunnerConversationState

    written = "保固期是十二個月，延長保固可以再加兩年，另外配件另計"
    state = RunnerConversationState.start().append_user("保固多久？").append_assistant(written)

    corrected = state.cut_off_after_the_run(heard_seconds=2.0)

    assert [turn.content for turn in corrected.turns] == ["保固多久？", "保固期是十二個月"]
    assert corrected.turns[-1].metadata.get("interrupted") is True
    assert corrected.revision == state.revision + 1


def test_an_interruption_with_no_timing_leaves_the_record_alone():
    """Something noticed the interruption without having played a note."""
    from playground.services.runner_conversation import RunnerConversationState

    written = "保固期是十二個月，延長保固可以再加兩年"
    state = RunnerConversationState.start().append_assistant(written)

    assert state.cut_off_after_the_run(heard_seconds=None).turns[-1].content == written


def test_the_page_can_correct_the_stored_answer_it_stopped_playing():
    from playground.app import create_app
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    app = create_app()
    app.config.update(TESTING=True)
    written = "保固期是十二個月，延長保固可以再加兩年，另外配件另計"

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = build_spec()
            current_session["runner_conversation"] = (
                RunnerConversationState.start().append_user("保固多久？").append_assistant(written).as_dict()
            )

        response = client.post("/playground/run/conversation/interrupted", json={"heard_seconds": 2.0})

        assert response.status_code == 200
        with client.session_transaction() as current_session:
            stored = RunnerConversationState.from_dict(current_session["runner_conversation"])
    assert [turn.content for turn in stored.turns] == ["保固多久？", "保固期是十二個月"]


def _interrupted_run(monkeypatch, *, delivered: str, heard_seconds: float):
    """A run stopped while it was answering, as the runner sees it."""
    from agentic_sdk.core import WorkflowResult
    from playground.services import runner_service
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    class FakeWorkflow:
        def run(self, *, user_message=None, **kwargs):
            memory = kwargs["memory"]
            return WorkflowResult(
                workflow_id="workflow",
                final_message=delivered,
                interrupted=True,
                interrupt_payload={"delivered": delivered, "heard_seconds": heard_seconds},
                memory=memory,
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_a, **_k: FakeWorkflow())
    return runner_service.run_agent(
        build_spec(),
        message="保固多久？",
        conversation_state=RunnerConversationState.start(),
    )


def test_the_stored_turn_says_it_was_cut_off(monkeypatch):
    """The next answer carries on only if the record says where it stopped.

    Without the marker the model reads a short answer as a complete one and
    starts again from the top, repeating what the person already heard.
    """
    execution = _interrupted_run(monkeypatch, delivered="保固期是十二個月", heard_seconds=2.0)

    turns = execution["conversation_update"]["turns"]
    assert turns[-1]["content"] == "保固期是十二個月"
    assert turns[-1]["metadata"].get("interrupted") is True


def test_an_answer_nobody_heard_is_not_replaced_by_something_it_never_said(monkeypatch):
    """Interrupted before a word landed: there is nothing to record.

    The fallback exists for a run that produced nothing to say. Reaching it
    here writes a sentence the agent never uttered into the conversation, and
    the person is then answered as though they had heard it.
    """
    execution = _interrupted_run(monkeypatch, delivered="", heard_seconds=0.0)

    assert execution["final_message"] == ""
    assert [turn["role"] for turn in execution["conversation_update"]["turns"]] == []
