"""What a workflow remembers after it stops running.

Observed the way an application uses it: build a store over a directory, run a
workflow, then build a fresh workflow and a fresh store over the same directory
and see what is still there. A new object over the same directory is what a
restarted process looks like.
"""

from __future__ import annotations

import time

from agentic_sdk import (
    CrossContextMemory,
    DirectAnswerAction,
    FileMemoryStore,
    PassThroughPerceive,
    PassThroughPlan,
    PassThroughRetrieve,
    Workflow,
)


def _workflow() -> Workflow:
    return Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
    )


def _said(store) -> list[str]:
    return [str(turn.content) for turn in store.turns]


def test_the_same_conversation_picks_up_where_it_left_off_after_a_restart(tmp_path):
    first = FileMemoryStore(root=str(tmp_path), session_id="one-conversation")
    _workflow().run("保固多久？", memory=first, session_id="one-conversation")

    restarted = FileMemoryStore(root=str(tmp_path), session_id="one-conversation")

    assert "保固多久？" in _said(restarted), "the conversation survived the process ending"
    assert len(_said(restarted)) == len(_said(first))


def test_a_second_run_adds_to_what_was_already_remembered(tmp_path):
    def store():
        return FileMemoryStore(root=str(tmp_path), session_id="one-conversation")

    _workflow().run("保固多久？", memory=store(), session_id="one-conversation")
    _workflow().run("可以退貨嗎？", memory=store(), session_id="one-conversation")

    remembered = _said(store())
    assert "保固多久？" in remembered
    assert "可以退貨嗎？" in remembered


def test_another_conversation_does_not_inherit_the_first_one_as_its_own_transcript(tmp_path):
    _workflow().run("保固多久？", memory=FileMemoryStore(root=str(tmp_path), session_id="morning"), session_id="morning")

    afternoon = FileMemoryStore(root=str(tmp_path), session_id="afternoon")

    assert _said(afternoon) == [], (
        "turns are this conversation; someone else's dialogue must not arrive as context"
    )


def test_another_conversation_can_still_find_what_the_first_one_said(tmp_path):
    _workflow().run("保固多久？", memory=FileMemoryStore(root=str(tmp_path), session_id="morning"), session_id="morning")

    afternoon = FileMemoryStore(root=str(tmp_path), session_id="afternoon")
    found = afternoon.search("default", query_text="保固", top_k=5)

    assert any("保固多久？" in result.entry.content for result in found), (
        "crossing conversations is what this memory is for, and searching is how it is reached"
    )


def test_two_workflows_do_not_see_each_other_memories(tmp_path):
    front_desk = Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        workflow_name="front-desk",
    )
    front_desk.run("保固多久？", memory=FileMemoryStore(root=str(tmp_path), session_id="s"), session_id="s")

    insole = FileMemoryStore(root=str(tmp_path), workflow_name="insole", session_id="s")

    assert _said(insole) == [], "one directory holds several workflows without mixing them"
    assert (tmp_path / "front-desk").is_dir(), "the workflow's own name decides the directory"


def test_each_remembered_turn_is_a_markdown_file_a_person_can_read(tmp_path):
    store = FileMemoryStore(root=str(tmp_path), workflow_name="front-desk")
    store.append_message("user", "保固多久？")

    files = sorted(tmp_path.rglob("*.md"))
    assert files, "the reason this memory is files is that a person can open them"
    written = files[0].read_text(encoding="utf-8")
    assert written.startswith("---\n"), "front matter first, so the fields are readable"
    assert "保固多久？" in written
    for field in ("entry_type:", "tier:", "created_at:", "session_id:"):
        assert field in written, f"{field} names where this came from and when"


def test_raw_turns_older_than_the_retention_window_are_forgotten(tmp_path):
    store = FileMemoryStore(root=str(tmp_path))
    store.append_message("user", "去年講過的事")
    for path in tmp_path.rglob("*.md"):
        stale = time.time() - 60 * 60 * 24 * 400
        path.write_text(path.read_text(encoding="utf-8").replace(
            f"created_at: {store.turns[0].created_at}", f"created_at: {stale}"
        ), encoding="utf-8")

    kept = FileMemoryStore(root=str(tmp_path), raw_retention_seconds=60 * 60 * 24 * 30)

    assert _said(kept) == [], "a retention window is what keeps the directory from growing forever"


def test_without_a_retention_window_nothing_is_forgotten(tmp_path):
    store = FileMemoryStore(root=str(tmp_path))
    store.append_message("user", "很久以前講過的事")

    kept = FileMemoryStore(root=str(tmp_path))

    assert _said(kept) == ["很久以前講過的事"], "not setting a window means keeping it"


def test_the_store_is_a_cross_context_memory(tmp_path):
    assert isinstance(FileMemoryStore(root=str(tmp_path)), CrossContextMemory)


def test_a_copy_made_for_one_run_still_writes_to_the_same_directory(tmp_path):
    store = FileMemoryStore(root=str(tmp_path))

    copied = store.copy_for_run()
    copied.append_message("user", "在複本上講的話")

    assert "在複本上講的話" in _said(FileMemoryStore(root=str(tmp_path))), (
        "a per-run copy that quietly stops persisting would lose the turn it was made for"
    )


def _named_workflow(name: str) -> Workflow:
    return Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
        workflow_name=name,
    )


def test_a_named_workflow_remembers_too(tmp_path):
    _named_workflow("front-desk").run(
        "保固多久？", memory=FileMemoryStore(root=str(tmp_path), session_id="s"), session_id="s"
    )

    back = FileMemoryStore(root=str(tmp_path), workflow_name="front-desk", session_id="s")

    assert "保固多久？" in _said(back), "naming the workflow must not lose its memory"
    assert back.search("front-desk", query_text="保固"), "and it must be findable from another conversation"


def test_the_workflow_name_it_runs_under_decides_which_memory_it_reads(tmp_path):
    _named_workflow("front-desk").run(
        "第一句", memory=FileMemoryStore(root=str(tmp_path), session_id="s"), session_id="s"
    )

    built_wrong = FileMemoryStore(root=str(tmp_path), workflow_name="some-other-name", session_id="s")
    _named_workflow("front-desk").run("第二句", memory=built_wrong, session_id="s")

    assert built_wrong.workflow_dir.name == "front-desk", "the workflow's name wins over the store's"
    assert "第一句" in _said(built_wrong), "and it reads what that workflow already remembered"


def test_two_ids_that_clean_to_the_same_name_stay_two_entries(tmp_path):
    from agentic_sdk import MemoryEntry

    store = FileMemoryStore(root=str(tmp_path), workflow_name="ids")
    store.append(MemoryEntry(content="A", entry_id="a b", role="user", workflow_name="ids"))
    store.append(MemoryEntry(content="B", entry_id="a-b", role="user", workflow_name="ids"))

    back = FileMemoryStore(root=str(tmp_path), workflow_name="ids")

    assert sorted(entry.entry_id for entry in back._entries) == ["a b", "a-b"], (
        "one entry silently replacing another would lose what was said"
    )


def test_a_copy_for_one_run_keeps_what_the_files_do_not_carry(tmp_path):
    from agentic_sdk import MemoryEntry

    store = FileMemoryStore(root=str(tmp_path), workflow_name="emb")
    store.append(MemoryEntry(content="C", entry_id="c1", role="user", workflow_name="emb", embedding=[1.0, 0.0]))

    copied = store.copy_for_run()

    assert copied._entries[0].embedding == [1.0, 0.0], (
        "a copy that re-read from disk would score every embedding search at nothing"
    )


def test_an_entry_belonging_to_another_workflow_is_written_under_that_workflow(tmp_path):
    from agentic_sdk import MemoryEntry

    store = FileMemoryStore(root=str(tmp_path), workflow_name="here")
    store.append(MemoryEntry(content="D", entry_id="d1", role="user", workflow_name="elsewhere"))

    assert (tmp_path / "elsewhere").is_dir(), "the entry says where it belongs, not the store that wrote it"
    assert _said(FileMemoryStore(root=str(tmp_path), workflow_name="elsewhere")) == ["D"]
