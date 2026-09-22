"""Deleting one thing a workflow remembered, and having it stay deleted.

A topic is what the memory synthesised out of several raw records. It rides in
front of the model every single turn, in the index, so one wrong topic is wrong
over and over. Somebody on the floor has to be able to strike it out.

Striking it out is not enough on its own. The raw records it was made from are
still there and still eligible, so the next time the memory collects, it makes
the same topic again out of the same records. Deleting therefore does two
things: the topic goes, and the records it was made from stop being eligible.

The records themselves stay. They are what a search has to be able to find —
what is being removed is a claim the memory was making, not what happened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_sdk import FileMemoryStore

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


@pytest.fixture
def patched(monkeypatch):
    def _patch(description="先前談過保固與退貨。"):
        monkeypatch.setattr(
            "agentic_sdk.memory.file_store.resolve_openai_client",
            lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text=description),
        )

    return _patch


def _remembering(tmp_path, **kwargs):
    return FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="s", **LLM_PARAMS, **kwargs)


def _said(store, how_many: int) -> None:
    for index in range(how_many):
        store.append_message("user", f"這是第{index}句話，講的是保固與退貨的細節。")
        store.append_message("assistant", f"好的，關於第{index}點我記下了。")


def _topics(store):
    return [entry for entry in store._entries if entry.tier == "topic"]


def _with_one_topic(tmp_path, patched):
    patched()
    store = _remembering(tmp_path, compaction_threshold_tokens=120)
    _said(store, 20)
    store.as_openai_messages()
    assert _topics(store), "the fixture has to actually produce one"
    return store


# --- what a workflow remembers can be listed -----------------------------


def test_what_this_workflow_remembers_can_be_read_off_it(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)

    remembered = store.remembered_topics()

    assert [topic.description for topic in remembered] == store.index_lines(), (
        "the list somebody reads and the list the model is shown are the same list, or the "
        "one they strike out is not the one that was wrong"
    )


def test_a_memory_that_has_collected_nothing_remembers_nothing(tmp_path):
    assert _remembering(tmp_path).remembered_topics() == []


# --- one can be struck out -----------------------------------------------


def test_striking_one_out_takes_it_out_of_what_the_model_is_shown(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    topic = store.remembered_topics()[0]

    store.forget_topic(topic.entry_id)

    assert topic.description not in store.index_lines()
    assert store.remembered_topics() == []


def test_striking_out_one_leaves_the_others(tmp_path, patched):
    patched("先前談過保固與退貨。")
    store = _remembering(tmp_path, compaction_threshold_tokens=120)
    _said(store, 20)
    store.as_openai_messages()
    store._entries.append(
        type(store._entries[0])(
            content="另一則主題的內容。",
            workflow_name="w",
            tier="topic",
            description="先前談過出貨時間。",
            role="system",
            session_id="s",
        )
    )
    struck = store.remembered_topics()[0]

    store.forget_topic(struck.entry_id)

    assert "先前談過出貨時間。" in store.index_lines()


def test_striking_out_something_that_is_not_there_says_so(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)

    with pytest.raises(LookupError):
        store.forget_topic("nothing-with-this-id")


def test_only_a_topic_can_be_struck_out(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    raw = next(entry for entry in store._entries if entry.tier == "raw")

    with pytest.raises(LookupError):
        store.forget_topic(raw.entry_id)


# --- it does not grow back -----------------------------------------------


def test_the_records_it_was_made_from_are_not_collected_again(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    topic = store.remembered_topics()[0]
    covered = [
        entry.entry_id
        for entry in store._entries
        if entry.metadata.get("synthesised_into") == topic.entry_id
    ]
    assert covered, "the fixture has to have covered something"

    store.forget_topic(topic.entry_id)
    store.compact(1)

    collected_again = [
        entry.entry_id
        for entry in store._entries
        if entry.entry_id in covered and entry.metadata.get("synthesised_into")
    ]
    assert collected_again == [], (
        "collecting the same records again makes the same topic again, and striking it out "
        "would be something somebody has to keep doing"
    )


def test_what_is_said_afterwards_is_still_learnt(tmp_path, patched):
    """Striking out a topic removes a claim; it does not make the memory deaf."""
    store = _with_one_topic(tmp_path, patched)
    struck = store.remembered_topics()[0]
    struck_out_records = {
        entry.entry_id
        for entry in store._entries
        if entry.metadata.get("synthesised_into") == struck.entry_id
    }
    store.forget_topic(struck.entry_id)

    for index in range(20):
        store.append_message("user", f"這是後來第{index}句話，講的是出貨時間的細節。")
        store.append_message("assistant", f"好的，關於後來第{index}點我記下了。")
    store.as_openai_messages()

    remembered = store.remembered_topics()
    assert remembered, "what is said after a topic is struck out is still collected"
    covered_by_the_new_one = [
        entry
        for entry in store._entries
        if entry.metadata.get("synthesised_into") == remembered[0].entry_id
    ]
    assert covered_by_the_new_one, "and it is made out of records, not out of nothing"
    assert not struck_out_records & {entry.entry_id for entry in covered_by_the_new_one}, (
        "out of records that are still eligible — the struck-out topic's are not among them"
    )


def test_it_is_still_gone_after_a_restart(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    store.forget_topic(store.remembered_topics()[0].entry_id)

    reopened = _remembering(tmp_path, compaction_threshold_tokens=120)

    assert reopened.remembered_topics() == []
    marked = [
        entry.entry_id
        for entry in reopened._entries
        if entry.metadata.get("forgotten_topic")
    ]
    assert marked, "the mark is what stops it coming back, so the mark has to be on disk"

    reopened.compact(1)

    collected_again = [
        entry.entry_id
        for entry in reopened._entries
        if entry.entry_id in marked and entry.metadata.get("synthesised_into")
    ]
    assert collected_again == [], (
        "a restart must not hand those records back to the next collection"
    )


# --- what happened is not rewritten --------------------------------------


def test_the_records_it_was_made_from_are_still_there(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    before = len([entry for entry in store._entries if entry.tier == "raw"])

    store.forget_topic(store.remembered_topics()[0].entry_id)

    assert len([entry for entry in store._entries if entry.tier == "raw"]) == before, (
        "what is being removed is a claim the memory was making, not what happened"
    )


def test_the_records_can_still_be_found_by_searching(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    store.forget_topic(store.remembered_topics()[0].entry_id)

    found = store.search("w", query_text="這是第0句話，講的是保固與退貨的細節。", top_k=50)

    assert any("這是第0句話" in result.entry.content for result in found), (
        "the records stay searchable — that is the whole of what they are for now"
    )


def test_the_records_do_not_come_back_as_conversation(tmp_path, patched):
    store = _with_one_topic(tmp_path, patched)
    store.forget_topic(store.remembered_topics()[0].entry_id)

    handed_over = " ".join(str(message.get("content", "")) for message in store.as_openai_messages())

    assert "這是第0句話" not in handed_over, (
        "they stopped being handed over when they were collected; striking out the topic "
        "removes the topic, it does not undo the collecting"
    )


# --- what the floor sees, and what they can strike out -------------------


def _remembering_agent(tmp_path, monkeypatch, patched):
    """A saved agent that carries things over, with one topic already in it."""
    from playground.services import runner_service

    patched()
    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))
    store = FileMemoryStore(
        root=str(tmp_path), workflow_name="default", session_id="s",
        compaction_threshold_tokens=120, **LLM_PARAMS,
    )
    _said(store, 20)
    store.as_openai_messages()
    assert _topics(store)
    return runner_service.memory_root()


def test_the_floor_can_read_what_this_agent_remembers(tmp_path, monkeypatch, patched):
    from playground.services.memory_admin import remembered_by

    _remembering_agent(tmp_path, monkeypatch, patched)

    remembered = remembered_by("default")

    assert [topic["description"] for topic in remembered] == ["先前談過保固與退貨。"]
    assert all(topic["id"] for topic in remembered), "each one needs to be nameable to strike it out"


def test_the_floor_reads_nothing_from_an_agent_that_carries_nothing(tmp_path, monkeypatch):
    from playground.services.memory_admin import remembered_by

    monkeypatch.setenv("PLAYGROUND_MEMORY_ROOT", str(tmp_path))

    assert remembered_by("default") == []


def test_the_floor_can_strike_one_out(tmp_path, monkeypatch, patched):
    from playground.services.memory_admin import forget, remembered_by

    _remembering_agent(tmp_path, monkeypatch, patched)
    topic = remembered_by("default")[0]

    forget("default", topic["id"])

    assert remembered_by("default") == []


def test_striking_out_something_that_is_not_there_is_refused(tmp_path, monkeypatch, patched):
    from playground.services.memory_admin import forget

    _remembering_agent(tmp_path, monkeypatch, patched)

    with pytest.raises(LookupError):
        forget("default", "nothing-with-this-id")


# --- reachable from the page ---------------------------------------------


def _client(monkeypatch, tmp_path, patched):
    from playground.app import create_app
    from support import build_spec

    _remembering_agent(tmp_path, monkeypatch, patched)
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["workflow_spec"] = build_spec(("memory_type", {"kind": "cross_context"}))
    return client


def test_the_page_can_ask_what_is_remembered(tmp_path, monkeypatch, patched):
    response = _client(monkeypatch, tmp_path, patched).get("/playground/run/memory")

    assert response.status_code == 200
    assert [topic["description"] for topic in response.get_json()["remembered"]] == ["先前談過保固與退貨。"]


def test_the_page_can_strike_one_out(tmp_path, monkeypatch, patched):
    client = _client(monkeypatch, tmp_path, patched)
    topic = client.get("/playground/run/memory").get_json()["remembered"][0]

    response = client.post("/playground/run/memory/forget", json={"id": topic["id"]})

    assert response.status_code == 200
    assert response.get_json()["remembered"] == [], (
        "the list comes back with the answer, so the page shows what is true now rather than "
        "what it hoped would happen"
    )


def test_striking_out_one_that_is_gone_is_refused_rather_than_reported_as_done(tmp_path, monkeypatch, patched):
    client = _client(monkeypatch, tmp_path, patched)

    response = client.post("/playground/run/memory/forget", json={"id": "nothing-with-this-id"})

    assert response.status_code == 404
    assert response.get_json()["forgotten"] is False


def test_the_panel_is_only_on_an_agent_that_carries_things_over():
    page = (Path(__file__).resolve().parents[1] / "playground" / "templates" / "runner.html").read_text(encoding="utf-8")

    assert "data-memory-modal" in page, "a list nobody can open is not a list"
    assert "{% if uses_cross_context_memory %}" in page, (
        "an agent that remembers nothing by design gets no panel about what it remembers"
    )


def test_the_panel_can_be_opened_and_knows_how_to_strike_one_out():
    page = (Path(__file__).resolve().parents[1] / "playground" / "templates" / "runner.html").read_text(encoding="utf-8")
    script = (Path(__file__).resolve().parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert "data-memory-open" in page, "a panel with no way to open it is not reachable"
    assert "/playground/run/memory/forget" in script, "and one with no way to strike out is read-only"
    assert "編輯" not in page.split("data-memory-modal", 1)[1].split("</section>", 1)[0], (
        "editing is deliberately absent: a line that reads fine and says the wrong thing is "
        "worse than no line, because nothing downstream will question it"
    )
