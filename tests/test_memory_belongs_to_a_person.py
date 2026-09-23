"""Who a workflow's memory is carried on behalf of.

"Carries things between conversations" left one question unanswered: between
whose conversations. The answer it fell into was "everyone using this agent",
so an agent on a shop floor would tell the next person what the last one said
— their order number, their name — without anybody having chosen that.

A memory belongs to the person it was built from. Their own conversations see
each other; another person's do not. Where nobody is identified there is only
one person to be — a program using the SDK on its own — and it reaches what it
wrote itself and nothing anybody else wrote, in either direction.

See ADR-0020.
"""

from __future__ import annotations

import pytest

from agentic_sdk import FileMemoryStore, InMemoryStore
from agentic_sdk.memory.in_context import build_module_messages

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


@pytest.fixture
def synthesising(monkeypatch):
    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="先前談過保固與退貨。"),
    )


def _store(tmp_path, session_id, user_id, **kwargs):
    return FileMemoryStore(
        root=str(tmp_path), workflow_name="客服",
        session_id=session_id, user_id=user_id, **LLM_PARAMS, **kwargs,
    )


def _talked_about_their_order(store, who: str) -> None:
    for index in range(20):
        store.append_message("user", f"我是{who}，我的訂單是 {who}{index}，要問保固。")
        store.append_message("assistant", f"{who}您好，訂單 {who}{index} 的保固是一年。")


def _remembers(tmp_path, who, synthesising) -> None:
    store = _store(tmp_path, f"{who}的第一段", who, compaction_threshold_tokens=120)
    _talked_about_their_order(store, who)
    store.as_openai_messages()
    assert store.remembered_topics(), "the fixture has to actually remember something"


# --- what another person's conversation sees ----------------------------


def test_another_persons_topics_are_not_put_in_front_of_the_model(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    theirs = _store(tmp_path, "李小姐的第一段", "李小姐")
    theirs.append_message("user", "我要問退貨")

    system = build_module_messages(theirs, system_prompt="SYSTEM")[0]["content"]
    assert "remembered_topics" not in system, (
        "the index goes in front of the model every single turn, so a topic from somebody "
        "else is somebody else's business every single turn"
    )


def test_another_persons_records_are_not_searchable(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    theirs = _store(tmp_path, "李小姐的第一段", "李小姐")
    found = theirs.search("客服", query_text="張先生 訂單 張先生1 保固", top_k=10)

    assert found == [], "searching is how the records are reached, so it is where they are kept apart"


def test_another_persons_conversation_is_not_carried_either(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    theirs = _store(tmp_path, "李小姐的第一段", "李小姐")
    theirs.append_message("user", "我要問退貨")

    assert [turn.content for turn in theirs.turns] == ["我要問退貨"]


# --- what their own second conversation sees ----------------------------


def test_their_own_later_conversation_still_picks_up_where_they_left_off(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    later = _store(tmp_path, "張先生的第二段", "張先生")
    later.append_message("user", "我要問退貨")

    system = build_module_messages(later, system_prompt="SYSTEM")[0]["content"]
    assert "先前談過保固與退貨。" in system, (
        "this is the whole point of carrying anything between conversations"
    )


def test_their_own_records_are_still_searchable_from_a_later_conversation(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    later = _store(tmp_path, "張先生的第二段", "張先生")
    found = later.search("客服", query_text="訂單 張先生1 保固", top_k=10)

    assert any("張先生1" in result.entry.content for result in found)


# --- nobody identified ---------------------------------------------------


def test_an_unidentified_run_carries_nothing_between_conversations(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    nobody = _store(tmp_path, "某一段", None)
    nobody.append_message("user", "我要問退貨")

    system = build_module_messages(nobody, system_prompt="SYSTEM")[0]["content"]
    assert "remembered_topics" not in system
    found = [result.entry.content for result in nobody.search("客服", query_text="張先生 保固", top_k=10)]
    assert not any("張先生" in content for content in found), (
        "carrying it to somebody who has not been identified is carrying it to a stranger"
    )
    assert found == ["我要問退貨"], "what it said itself is still its own"


def test_what_an_unidentified_run_says_is_not_handed_to_anybody_else(tmp_path, synthesising):
    nobody = _store(tmp_path, "某一段", None, compaction_threshold_tokens=120)
    _talked_about_their_order(nobody, "某人")
    nobody.as_openai_messages()

    someone = _store(tmp_path, "張先生的第一段", "張先生")
    assert someone.search("客服", query_text="某人 訂單 某人1", top_k=10) == []
    assert "remembered_topics" not in build_module_messages(someone, system_prompt="SYSTEM")[0]["content"]


def test_records_written_before_anybody_was_identified_stay_where_they_are(tmp_path, synthesising):
    """Memory already on disk has no owner, and guessing one would be a leak."""
    legacy = FileMemoryStore(root=str(tmp_path), workflow_name="客服", session_id="舊的", **LLM_PARAMS)
    legacy.append_message("user", "舊的紀錄，沒有人的標記。")

    someone = _store(tmp_path, "張先生的第一段", "張先生")

    assert someone.search("客服", query_text="舊的紀錄 沒有人的標記", top_k=10) == []


# --- it survives a restart ----------------------------------------------


def test_who_it_belongs_to_is_written_down(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    reopened = _store(tmp_path, "張先生的第三段", "張先生")

    assert "先前談過保固與退貨。" in build_module_messages(reopened, system_prompt="SYSTEM")[0]["content"]


def test_a_memory_kept_only_in_the_process_keeps_people_apart_too():
    theirs = InMemoryStore(workflow_name="客服", session_id="a", user_id="張先生")
    theirs.append_message("user", "我是張先生，訂單 A1。")

    other = InMemoryStore(workflow_name="客服", session_id="b", user_id="李小姐")
    other._entries = theirs._entries

    assert other.search("客服", query_text="張先生 訂單 A1", top_k=10) == []


# --- the ways round it that the review found ----------------------------


def test_nobody_can_strike_out_a_topic_that_is_not_theirs(tmp_path, synthesising):
    """Naming an id is not the same as owning what it names."""
    _remembers(tmp_path, "張先生", synthesising)
    theirs = _store(tmp_path, "張先生的第二段", "張先生")
    topic = theirs.remembered_topics()[0]

    somebody_else = _store(tmp_path, "李小姐的第一段", "李小姐")
    with pytest.raises(LookupError):
        somebody_else.forget_topic(topic.entry_id)

    assert _store(tmp_path, "張先生的第三段", "張先生").remembered_topics(), (
        "a topic somebody else struck out is a topic its owner never chose to lose"
    )


def test_sharing_a_conversation_id_does_not_share_the_conversation(tmp_path, synthesising):
    """Two people can end up on one conversation id; that must not be enough."""
    mine = _store(tmp_path, "共用的識別碼", "張先生")
    mine.append_message("user", "我是張先生，訂單 A1。")

    theirs = _store(tmp_path, "共用的識別碼", "李小姐")

    assert [turn.content for turn in theirs.turns] == []
    assert "訂單 A1" not in " ".join(
        str(message.get("content", "")) for message in theirs.as_openai_messages()
    )


def test_collecting_never_rewrites_a_topic_that_is_not_theirs(tmp_path, synthesising):
    """Updating a topic reads its content back; reading it is the leak."""
    _remembers(tmp_path, "張先生", synthesising)
    before = _store(tmp_path, "張先生的第二段", "張先生").remembered_topics()[0].content

    theirs = _store(tmp_path, "共用的識別碼", "李小姐", compaction_threshold_tokens=120)
    _talked_about_their_order(theirs, "李小姐")
    theirs.as_openai_messages()

    after = _store(tmp_path, "張先生的第三段", "張先生").remembered_topics()
    assert [topic.content for topic in after] == [before], (
        "synthesising over somebody else's topic feeds their content to this person's endpoint "
        "and overwrites what they remembered"
    )


def test_clearing_only_clears_what_this_run_can_see(tmp_path, synthesising):
    _remembers(tmp_path, "張先生", synthesising)

    _store(tmp_path, "李小姐的第一段", "李小姐").clear()

    assert _store(tmp_path, "張先生的第二段", "張先生").remembered_topics(), (
        "wiping another person's records is the same mistake as reading them, with less to "
        "undo it"
    )
