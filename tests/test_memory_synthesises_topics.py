"""What the memory does with a conversation that got too long to carry.

Observed the way a module sees it: ask the store for the messages it would hand
over, and look at what came back. Synthesis is the memory's own job — it takes
no module slot and appears in no protocol — so the only place to watch it is
the moment the memory hands its contents over.
"""

from __future__ import annotations

from agentic_sdk import FileMemoryStore, MemoryEntry

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


def _store(tmp_path, **kwargs):
    return FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="s", **kwargs)


def _say(store, how_many: int, prefix: str = "這是第") -> None:
    for index in range(how_many):
        store.append_message("user", f"{prefix}{index}句話，講的是保固與退貨的細節。")
        store.append_message("assistant", f"好的，關於第{index}點我記下了。")


def _topics(store) -> list[MemoryEntry]:
    return [entry for entry in store._entries if entry.tier == "topic"]


def test_without_a_threshold_nothing_is_synthesised(tmp_path):
    store = _store(tmp_path)
    _say(store, 20)

    store.as_openai_messages()

    assert _topics(store) == [], "compaction is off until somebody turns it on"


def test_a_conversation_under_the_threshold_is_left_alone(tmp_path):
    store = _store(tmp_path, compaction_threshold_tokens=100_000, **LLM_PARAMS)
    _say(store, 3)
    before = store.as_openai_messages()

    assert _topics(store) == []
    assert store.as_openai_messages() == before


def test_a_conversation_over_the_threshold_is_synthesised_down_under_it(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)

    handed_over = store.as_openai_messages()

    assert _topics(store), "the oldest of it became a topic"
    assert store.tokens_in(handed_over) <= 120, "and what is handed over now fits"


def test_the_oldest_goes_first_and_the_newest_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)

    handed_over = " ".join(str(message["content"]) for message in store.as_openai_messages())

    assert "這是第19句話" in handed_over, "what was just said is the last thing to go"
    assert "這是第0句話" not in handed_over, "and the oldest is what went"


def test_what_was_synthesised_is_still_findable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()

    found = store.search("w", query_text="這是第0句話", top_k=50)

    assert any("這是第0句話" in result.entry.content for result in found), (
        "raw entries are kept for searching, which is the whole reason they are not deleted"
    )


def test_a_topic_carries_one_line_saying_what_it_is_about(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()

    topic = _topics(store)[0]
    assert topic.description, "that line is what the index is made of"
    assert topic.description in store.index_lines()


def test_the_index_is_rebuilt_from_the_topics_rather_than_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()

    reopened = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)

    assert reopened.index_lines() == store.index_lines(), "read back off the topics, not off a file of its own"


def test_synthesis_is_announced_so_nobody_wonders_why_it_went_quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    said: list[dict] = []
    store = _store(tmp_path, compaction_threshold_tokens=120, on_event=said.append, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()

    assert [event for event in said if event.get("type") == "memory_compacted"], (
        "the person is told their earlier turns were collected, not left to notice it"
    )


def test_a_memory_that_cannot_synthesise_is_simply_left_alone(tmp_path):
    from agentic_sdk import InMemoryStore

    assert not hasattr(InMemoryStore(), "compact"), (
        "whoever needs to know asks by this, so a memory that cannot collect must not look as if it can"
    )
    assert hasattr(_store(tmp_path), "compact")


def _patched(monkeypatch, **kwargs):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(**kwargs),
    )


def test_a_topic_about_something_else_is_a_second_topic_not_an_update(tmp_path, monkeypatch):
    _patched(monkeypatch, synthesis_description="先前談過保固與退貨的條件。")
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()

    _patched(monkeypatch, synthesis_description="接著討論了出貨時程與包裝方式。")
    _say(store, 20, prefix="後來第")
    store.as_openai_messages()

    assert len(store.index_lines()) == 2, "two subjects are two lines, not one overwritten one"


def test_saying_the_same_thing_again_updates_the_topic_instead_of_adding_a_line(tmp_path, monkeypatch):
    _patched(monkeypatch, synthesis_description="先前談過保固與退貨的條件。")
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(store, 20)
    store.as_openai_messages()
    _say(store, 20, prefix="又說第")
    store.as_openai_messages()

    assert len(store.index_lines()) == 1, (
        "the index is what sits in front of the model every exchange, so it must not collect duplicates"
    )


def test_one_conversation_never_rewrites_another_conversation_topic(tmp_path, monkeypatch):
    _patched(monkeypatch, synthesis_description="先前談過保固與退貨的條件。")
    morning = FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="morning",
                              compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(morning, 20)
    morning.as_openai_messages()
    before = [entry.content for entry in morning._entries if entry.tier == "topic"]

    afternoon = FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="afternoon",
                                compaction_threshold_tokens=120, **LLM_PARAMS)
    _say(afternoon, 20)
    afternoon.as_openai_messages()

    reopened = FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="morning", **LLM_PARAMS)
    topics = [entry for entry in reopened._entries if entry.tier == "topic"]
    mine = [entry.content for entry in topics if entry.session_id == "morning"]

    assert mine == before, "the morning's topic still says what the morning said"
    assert len([entry for entry in topics if entry.session_id == "afternoon"]) == 1, (
        "the afternoon made its own, rather than its exchanges going under a topic it cannot see"
    )


def test_a_copy_made_for_one_run_can_still_collect(tmp_path, monkeypatch):
    _patched(monkeypatch)
    store = _store(tmp_path, compaction_threshold_tokens=120, **LLM_PARAMS)

    copied = store.copy_for_run()

    assert copied.compaction_threshold_tokens == 120, (
        "the workflow hands modules a copy, so a copy that cannot collect means this never runs at all"
    )
    _say(copied, 20)
    copied.as_openai_messages()
    assert [entry for entry in copied._entries if entry.tier == "topic"]


def test_an_endpoint_that_will_not_answer_does_not_stop_the_conversation(tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise RuntimeError("synthesis endpoint unavailable")

    monkeypatch.setattr("agentic_sdk.memory.file_store.resolve_openai_client", refuse)
    said: list[dict] = []
    store = _store(tmp_path, compaction_threshold_tokens=120, on_event=said.append, **LLM_PARAMS)
    _say(store, 20)

    handed_over = store.as_openai_messages()

    assert handed_over, "handing over too much beats handing over nothing"
    assert [event for event in said if event.get("type") == "memory_compaction_failed"]
