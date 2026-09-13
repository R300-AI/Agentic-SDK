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


def test_a_run_registers_itself_so_it_can_be_stopped(monkeypatch):
    """Without this the endpoint has a name but nothing answering to it.

    Asked while the answer is being produced, because that is the only time
    stopping it means anything. Once it has finished there is nothing left to
    stop, and the session says so rather than pretending otherwise.
    """
    from agentic_sdk.core import WorkflowResult
    from playground.services import runner_service

    from support import build_spec

    stoppable = {}

    class FakeWorkflow:
        def run(self, *, user_message=None, **kwargs):
            stoppable["while answering"] = registry.token("session-e") is not None
            return WorkflowResult(
                workflow_id="workflow", final_message="十二個月。", memory=kwargs.get("memory")
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_a, **_k: FakeWorkflow())
    runner_service.run_agent(
        build_spec(), message="保固多久？", endpoint_selections={}, voice_session_id="session-e"
    )

    assert stoppable["while answering"] is True
    assert registry.token("session-e") is None


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


def test_an_answer_that_has_finished_cannot_be_interrupted():
    """A finished run is not something the person can still stop.

    Speaking outlives the run, so someone talking over the tail of an answer
    arrives here long after it ended. Saying the interruption stopped something
    leaves the page believing the record was corrected for it, when nothing
    was: the turn is already stored whole.
    """
    from playground.services.voice_session import VoiceSessionRegistry

    registry = VoiceSessionRegistry()
    registry.open("session-1")
    registry.settled("session-1")

    assert registry.interject("session-1", heard_seconds=2.4) is False


def test_the_session_stays_open_for_the_next_question(monkeypatch):
    """Settling one answer must not close the microphone behind it."""
    from playground.services.voice_session import VoiceSessionRegistry

    registry = VoiceSessionRegistry()
    registry.open("session-1")
    registry.settled("session-1")
    token = registry.open("session-1")

    assert registry.interject("session-1", heard_seconds=1.0) is True
    assert token.cancelled is True


def test_a_run_lets_go_of_its_voice_session_when_it_ends(monkeypatch):
    """The runner has to say when the answer is over; nothing else knows."""
    from playground.services import runner_service
    from playground.services.voice_session import registry

    session_id = "session-finished"
    _completed_run(monkeypatch, voice_session_id=session_id)

    assert registry.interject(session_id, heard_seconds=2.4) is False


def _completed_run(monkeypatch, *, voice_session_id: str):
    from agentic_sdk.core import WorkflowResult
    from playground.services import runner_service
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    class FakeWorkflow:
        def run(self, *, user_message=None, **kwargs):
            return WorkflowResult(
                workflow_id="workflow",
                final_message="這週六 B 場整天都還可以訂。",
                memory=kwargs["memory"],
            )

    monkeypatch.setattr(runner_service, "build_workflow", lambda *_a, **_k: FakeWorkflow())
    return runner_service.run_agent(
        build_spec(),
        message="這週六下午還有場地嗎？",
        conversation_state=RunnerConversationState.start(),
        voice_session_id=voice_session_id,
    )


def test_the_correction_finds_the_answer_even_after_the_next_question_lands():
    """Talking over an answer does two things at once: interrupts, and asks.

    The new question reaches the record first, because a run registers what
    was said as soon as it starts, while the correction takes a round trip
    through the page. A correction that insists on the last turn finds a
    question sitting there and does nothing, and the answer nobody finished
    hearing stays in the record whole.
    """
    from playground.services.runner_conversation import RunnerConversationState

    written = "保固期是十二個月，延長保固可以再加兩年，另外配件另計"
    state = (
        RunnerConversationState.start()
        .append_user("保固多久？")
        .append_assistant(written)
        .append_user("那延長保固呢？")
    )

    corrected = state.cut_off_after_the_run(heard_seconds=2.0)

    assert [turn.content for turn in corrected.turns] == [
        "保固多久？",
        "保固期是十二個月",
        "那延長保固呢？",
    ]
    assert corrected.turns[1].metadata.get("interrupted") is True


def test_a_new_question_stops_the_answer_still_running():
    """Two answers at once is not two answers: it is one person being talked at.

    Measured on the deployment: a second question sent three seconds into a
    long answer left the first one running to completion — 895 characters,
    billed and spoken, for a question the person had already moved on from.
    """
    from playground.services.voice_session import VoiceSessionRegistry

    registry = VoiceSessionRegistry()
    first = registry.open("session-1")

    registry.open("session-1")

    assert first.cancelled is True
    assert first.reason == "superseded"


def test_being_interrupted_does_not_read_as_the_flow_breaking():
    """Talking over an answer is steering, not a fault.

    Seen on the deployment: interrupting left 「流程中止 / cancelled」 on screen —
    the wording for a safety limit stopping the workflow, with an untranslated
    reason under it. The person did it on purpose and it reads as a breakage.
    """
    from playground.services import runner_service

    config = runner_service.BuilderSourceConfig(workflow_name="羽球館")
    event = runner_service._process_event_for_workflow_event(
        config,
        {
            "type": "stage",
            "phase": "abort",
            "status": "interrupted",
            "module": "action",
            "label": "產生回覆",
            "schema": {"label": "產生回覆", "fields": []},
            "reason": "interjection",
            "interrupted": True,
            "visit_id": "v1",
        },
    )

    assert event is not None
    assert "中止" not in str(event["title"])
    assert "cancelled" not in str(event["description"]).lower()
    assert "插話" in str(event["title"]) + str(event["description"])


def test_a_run_dropped_for_a_new_question_does_not_claim_someone_talked_over_it():
    """Two ways a turn ends early, and they are not the same event.

    Someone talking over the answer heard part of it; someone asking a new
    question was not necessarily listening at all. The trace said 「有人插話」
    for both, which tells whoever is tuning the agent the wrong thing about
    what just happened.
    """
    from types import SimpleNamespace

    from playground.services import runner_service

    superseded = SimpleNamespace(interrupted=True, interrupt_payload={"reason": "superseded"})

    note = runner_service._interruption_note(superseded)

    assert "插話" not in note
    assert "新的問題" in note


def test_an_answer_is_not_thrown_away_because_another_turn_landed_first():
    """連著講兩句時，兩輪的寫回會交錯，後到的那一筆版本號已經過期。

    線上實測：連續四次語音輸入之後，讀回對話紀錄只剩使用者發言——那一輪所有
    助理回合都被丟掉了，畫面要使用者重新整理頁面。內容相容的寫回應該接到目前
    狀態上，而不是整筆拒絕。
    """
    from playground.app import create_app
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    app = create_app()
    app.config.update(TESTING=True)
    written = "這週六晚上 A 場 20:00-22:00 可訂，B 場 18:00-22:00 可訂。"

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = build_spec()
            started = RunnerConversationState.start().append_user("這週六晚上還有場地嗎？").append_assistant(written)
            current_session["runner_conversation"] = started.as_dict()

        # 第二輪在第一輪的紀錄上算出自己的更新⋯⋯
        second = {**started.append_user("那費率呢？").append_assistant("尖峰每面每小時 400 元。").as_dict(), "appended": 2}
        # ⋯⋯但送出之前，打斷的更正先落地了，第一則助理回合被截短。
        client.post("/playground/run/conversation/interrupted", json={"heard_seconds": 2.0})

        response = client.post("/playground/run/conversation/commit", json={"conversation_update": second})

        assert response.status_code == 200, response.get_json()
        with client.session_transaction() as current_session:
            stored = RunnerConversationState.from_dict(current_session["runner_conversation"])

    contents = [turn.content for turn in stored.turns]
    assert "尖峰每面每小時 400 元。" in contents, "後到的那一輪回答被丟掉了"
    assert written not in contents, "截短過的那一則又被寫回完整版"


def test_an_answer_nobody_heard_is_not_resurrected_by_the_next_commit():
    """打斷得夠早，那一則就整則不存在——下一筆寫回不該把它接回來。

    它是在舊紀錄上算出來的，裡面還帶著那一則。用內容前綴去對齊時，長度對不上
    就只比對到較短的一邊，被移除的那一則於是混進「新增的回合」裡。
    """
    from playground.app import create_app
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    app = create_app()
    app.config.update(TESTING=True)
    unheard = "這週六晚上 A 場 20:00-22:00 可訂，B 場 18:00-22:00 可訂。"

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = build_spec()
            started = RunnerConversationState.start().append_user("這週六晚上還有場地嗎？").append_assistant(unheard)
            current_session["runner_conversation"] = started.as_dict()

        second = {**started.append_user("那費率呢？").append_assistant("尖峰每面每小時 400 元。").as_dict(), "appended": 2}
        # 一個字都沒聽到：那一則整則移除。
        client.post("/playground/run/conversation/interrupted", json={"heard_seconds": 0.0})

        response = client.post("/playground/run/conversation/commit", json={"conversation_update": second})

        assert response.status_code == 200, response.get_json()
        with client.session_transaction() as current_session:
            stored = RunnerConversationState.from_dict(current_session["runner_conversation"])

    contents = [turn.content for turn in stored.turns]
    assert unheard not in contents, "沒人聽到的那一則被下一筆寫回接了回來"
    assert "尖峰每面每小時 400 元。" in contents, "後到的那一輪回答被丟掉了"


def test_two_different_questions_are_not_merged_because_one_starts_the_other():
    """「好」與「好的，謝謝」是兩句話，不是同一句被截短。

    截短只會發生在助理回合；對使用者發言套用前綴規則，等於把兩段不同的對話
    當成同一段接起來。
    """
    from playground.services.runner_conversation import RunnerConversationState

    from playground.app import create_app

    from support import build_spec

    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = build_spec()
            current = RunnerConversationState.start().append_user("好")
            current_session["runner_conversation"] = current.as_dict()

        # 沒有聲明自己新增了幾則，版本也對不上：這是另一段對話，不是延伸。
        stale = {
            **current.as_dict(),
            "revision": current.revision + 5,
            "turns": [{"role": "user", "content": "好的，謝謝"}, {"role": "assistant", "content": "不客氣。"}],
        }
        response = client.post("/playground/run/conversation/commit", json={"conversation_update": stale})

    assert response.status_code == 409


def test_the_cut_off_mark_survives_the_next_commit():
    """標記是下一輪提示知道「話沒講完」的唯一依據。

    截短由更正落下，標記也在那一刻寫上；下一輪的寫回接在它後面時，若把那一則
    連同標記一起換掉，agent 就會以為對方聽完了整段。
    """
    from playground.app import create_app
    from playground.services.runner_conversation import RunnerConversationState

    from support import build_spec

    app = create_app()
    app.config.update(TESTING=True)
    written = "這週六晚上 A 場 20:00-22:00 可訂，B 場 18:00-22:00 可訂。"

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["workflow_spec"] = build_spec()
            started = RunnerConversationState.start().append_user("這週六還有場地嗎？").append_assistant(written)
            current_session["runner_conversation"] = started.as_dict()

        client.post("/playground/run/conversation/interrupted", json={"heard_seconds": 2.0})
        second = {**started.append_user("那費率呢？").append_assistant("尖峰每面每小時 400 元。").as_dict(), "appended": 2}
        client.post("/playground/run/conversation/commit", json={"conversation_update": second})

        with client.session_transaction() as current_session:
            stored = RunnerConversationState.from_dict(current_session["runner_conversation"])

    cut_off = [turn for turn in stored.turns if (turn.metadata or {}).get("interrupted")]
    assert cut_off, "截短過的那一則失去了「被打斷」的標記"
    assert cut_off[-1].content == "這週六晚上 A 場"
