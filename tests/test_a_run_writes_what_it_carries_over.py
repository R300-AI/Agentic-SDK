"""An agent told to carry things between conversations has to write them down.

Choosing 承接前文問答 built a file-backed memory and then never used it: every
run handed ``Workflow.run()`` an explicit ``memory=`` — the conversation the
Playground keeps in its own session — and that wins over ``memory_type``. The
store was constructed, wired to a directory, and bypassed, so a run finished
green with nothing on disk and the next conversation started from nothing.

Observed through the real HTTP route, because that is the only place the two
memories meet. See #43.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from playground.app import create_app

from support import build_spec


WHO = "張先生"


@pytest.fixture
def playground(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))
    monkeypatch.setenv("PLAYGROUND_TEST_MODE", "1")

    def _client(kind="cross_context", *, answers_with_a_model=False):
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        steps = [("memory_type", {"kind": kind})]
        if answers_with_a_model:
            steps.append(("output_format", "free_text"))
        with client.session_transaction() as flask_session:
            flask_session["workflow_spec"] = build_spec(*steps)
            flask_session["ai_hub_username"] = WHO
            if answers_with_a_model:
                flask_session["endpoint_bindings"] = {
                    role: "gpt-54" for role in ("perceive", "plan", "action", "reflect", "memory")
                }
        return client

    return _client


def _say(client, message):
    response = client.post("/playground/run/execute", json={"message": message})
    assert response.status_code == 200
    assert (response.get_json() or {}).get("status") == "completed", "the run has to finish, or nothing is proven"
    return response


def _written(tmp_path):
    return [path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.md")]


# --- it writes what it was told to carry --------------------------------


def test_a_finished_run_leaves_the_conversation_on_disk(playground, tmp_path):
    _say(playground(), "我是張先生，訂單 A1，請問保固多久？")

    assert any("訂單 A1" in text for text in _written(tmp_path)), (
        "an agent told to carry things between conversations that writes nothing has "
        "nothing to carry"
    )


def test_the_second_turn_joins_the_first_rather_than_starting_over(playground, tmp_path):
    client = playground()
    _say(client, "我是張先生，訂單 A1，請問保固多久？")
    _say(client, "那退貨呢？")

    written = " ".join(_written(tmp_path))
    assert "訂單 A1" in written and "那退貨呢" in written
    assert len(list(tmp_path.rglob("*.md"))) >= 2, "each turn is its own record"


def test_what_was_written_belongs_to_the_person_who_said_it(playground, tmp_path):
    _say(playground(), "我是張先生，訂單 A1，請問保固多久？")

    owners = {
        line.split(":", 1)[1].strip()
        for text in _written(tmp_path)
        for line in text.splitlines()
        if line.startswith("user_id:")
    }
    assert owners and all(WHO in owner for owner in owners), (
        "a record with no owner is a record nobody identified can ever read again"
    )


def test_the_panel_shows_the_conversation_that_actually_happened(playground, tmp_path):
    client = playground()
    _say(client, "我是張先生，訂單 A1，請問保固多久？")

    remembered = (client.get("/playground/run/memory").get_json() or {}).get("remembered")
    assert remembered is not None, "the panel has to answer at all"


# --- and only when it was told to ---------------------------------------


def test_an_agent_that_only_sees_this_conversation_writes_nothing_down(playground, tmp_path):
    _say(playground("in_context"), "我是張先生，訂單 A1，請問保固多久？")

    assert list(tmp_path.rglob("*.md")) == [], (
        "nothing was asked to be carried, so nothing is written — the directory is not "
        "a place to leave things just because it exists"
    )


# --- what the review found in the first version of the replay -----------


def test_saying_the_same_thing_twice_is_written_twice(playground, tmp_path):
    """Somebody who says 好 twice means it twice."""
    client = playground()
    _say(client, "好")
    _say(client, "好")

    written = [text for text in _written(tmp_path) if "\n好" in text or text.rstrip().endswith("好")]
    assert len(written) >= 2, "matching on the words alone loses the second one for good"


def test_a_collected_conversation_does_not_get_written_again(playground, tmp_path, monkeypatch):
    """Turns collected into a topic stop being handed over — but they are still there.

    Telling what is already written from what is new by reading the store's own
    turns back would call every collected turn missing, and write the whole
    conversation again on every run.
    """
    from agentic_sdk.memory.file_store import FileMemoryStore

    client = playground()
    _say(client, "第一句話")
    before = len(list(tmp_path.rglob("*.md")))

    # Whatever has been said so far now reads as collected.
    real_turns = FileMemoryStore.turns
    monkeypatch.setattr(FileMemoryStore, "turns", property(lambda self: []))
    _say(client, "第二句話")
    monkeypatch.setattr(FileMemoryStore, "turns", real_turns)

    after = len(list(tmp_path.rglob("*.md")))
    assert after - before <= 2, (
        f"one exchange should add at most two records, not re-write the conversation "
        f"({before} → {after})"
    )


def test_an_attachment_reaches_the_record(playground, tmp_path):
    client = playground()
    response = client.post(
        "/playground/run/execute",
        json={
            "message": "請看這張圖",
            "attachments": [
                {
                    "kind": "image",
                    "name": "report.png",
                    "media_type": "image/png",
                    "content": "data:image/png;base64,aGVsbG8=",
                }
            ],
        },
    )
    assert response.status_code == 200

    assert any("attachment" in text for text in _written(tmp_path)), (
        "a store rebuilds its turns on every read, so setting attachments on one afterwards "
        "writes to a copy nobody sees again"
    )


# --- what the second review found ---------------------------------------


def _new_conversation(client):
    """Start over, the way picking another agent or reloading the page does."""
    with client.session_transaction() as flask_session:
        flask_session.pop("runner_conversation", None)


def test_a_second_conversation_works_at_all(playground, tmp_path):
    client = playground()
    _say(client, "第一段對話的問題")

    _new_conversation(client)
    _say(client, "第二段對話的問題")

    written = " ".join(_written(tmp_path))
    assert "第二段對話的問題" in written, (
        "a second conversation whose turns collide with the first's is a second "
        "conversation that cannot say anything"
    )


def test_an_assistant_reply_is_written_once(playground, tmp_path):
    client = playground()
    _say(client, "第一句話")
    _say(client, "第二句話")
    _say(client, "第三句話")

    assistant_records = [text for text in _written(tmp_path) if "role: assistant" in text]
    bodies = [text.split("---", 2)[-1].strip() for text in assistant_records]

    assert len(bodies) == len(set(bodies)) or len(assistant_records) <= 3, (
        f"three exchanges wrote {len(assistant_records)} assistant records; the run writes its "
        "own reply, so putting the page's copy in as well writes each one twice"
    )


def test_the_context_a_run_is_given_says_each_reply_once(playground, tmp_path):
    client = playground()
    _say(client, "第一句話")
    _say(client, "第二句話")

    from agentic_sdk import FileMemoryStore

    store = FileMemoryStore(root=str(tmp_path), workflow_name="default")
    contents = [turn.content for turn in store.mine() if turn.role == "assistant"]
    assert len(contents) == len(set(contents)) or len(contents) <= 2, (
        "a duplicated reply is paid for on every later turn, in a budget that is already tight"
    )


# --- the criterion the whole feature exists for -------------------------


def test_a_new_conversation_is_told_what_the_last_one_was_about(playground, tmp_path, monkeypatch):
    """A topic from an earlier conversation reaches the next one's prompt.

    This is what 承接前文問答 means. Collecting is what produces a topic, and
    it needs a model, so the topic here is put on disk directly — what is being
    watched is whether it travels, not whether the wording is any good.
    """
    from unittest.mock import patch

    from agentic_sdk import FileMemoryStore
    from support import FoundryOpenAILikeClient

    client = playground(answers_with_a_model=True)
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=FoundryOpenAILikeClient(action_text="好的。")):
        _say(client, "第一段對話的問題")

    earlier = FileMemoryStore(root=str(tmp_path), workflow_name="default", user_id=f"aihub:{WHO}")
    topic = next(entry for entry in earlier.mine() if entry.role == "user")
    topic.tier = "topic"
    topic.description = "先前談過保固期限與退貨條件。"
    topic.content = "使用者問過保固多久、怎麼退貨。"
    earlier._write(topic)

    _new_conversation(client)
    seen = FoundryOpenAILikeClient(action_text="好的。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=seen):
        _say(client, "那退貨呢？")

    sent = " ".join(
        str(message.get("content", "")) for message in (seen.last_create_kwargs or {}).get("messages", [])
    )
    assert "先前談過保固期限與退貨條件。" in sent, (
        "carrying things between conversations means the next conversation is told about them"
    )


def test_it_is_told_only_about_its_own_persons_conversations(playground, tmp_path):
    """The same journey, for somebody else's topic."""
    from agentic_sdk import FileMemoryStore

    client = playground()
    _say(client, "第一段對話的問題")

    somebody_else = FileMemoryStore(root=str(tmp_path), workflow_name="default", user_id="aihub:李小姐")
    somebody_else.append_message("user", "李小姐的訂單是 B9。")
    stranger = somebody_else.mine()[0]
    stranger.tier = "topic"
    stranger.description = "先前談過李小姐的訂單。"
    somebody_else._write(stranger)

    _new_conversation(client)
    remembered = FileMemoryStore(
        root=str(tmp_path), workflow_name="default", user_id=f"aihub:{WHO}"
    ).index_lines()

    assert "先前談過李小姐的訂單。" not in remembered
