"""Looking things up in memory is not a module you choose; it is the floor.

Observed through a run: mount each retrieve module in turn, give the workflow a
memory that already holds something, and see whether the lookup finds it. What
differs between the modules is how they search external sources — documents,
keyword lists — not whether they can reach what this agent already knows.
"""

from __future__ import annotations

import pytest

from agentic_sdk import (
    DirectAnswerAction,
    FileMemoryStore,
    KeywordRetrieve,
    PassThroughPerceive,
    PassThroughPlan,
    PassThroughRetrieve,
    SemanticRetrieve,
    Workflow,
)
from agentic_sdk.memory.protocol import MemoryEntry


REMEMBERED = "這位客人上次買的是 26 號的鞋。"


def _memory_holding_something(tmp_path):
    store = FileMemoryStore(root=str(tmp_path), workflow_name="default", session_id="earlier")
    store.append(
        MemoryEntry(
            content=REMEMBERED,
            workflow_name="default",
            entry_type="conversation_turn",
            role="assistant",
            session_id="earlier",
        )
    )
    return FileMemoryStore(root=str(tmp_path), workflow_name="default", session_id="now")


def _run_with(retrieve, tmp_path):
    return Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=retrieve,
        action=DirectAnswerAction(),
    ).run("鞋號", memory=_memory_holding_something(tmp_path), session_id="now")


def _looked_up(result) -> str:
    from agentic_sdk.core import ContextEntryType

    return " ".join(
        str(entry.content) for entry in result.entries if entry.type == ContextEntryType.RETRIEVED
    )


@pytest.mark.parametrize(
    "retrieve",
    [
        PassThroughRetrieve(),
        KeywordRetrieve(items=[{"keywords": ["保固"], "content": "保固兩年。"}]),
    ],
    ids=["pass_through", "keyword"],
)
def test_every_retrieve_module_reaches_what_the_agent_already_knows(retrieve, tmp_path):
    result = _run_with(retrieve, tmp_path)

    assert REMEMBERED in _looked_up(result), (
        "memory is not a module you pick; choosing a different lookup must not lose it"
    )


def test_the_semantic_module_still_reaches_it_too(tmp_path):
    result = _run_with(SemanticRetrieve(), tmp_path)

    assert REMEMBERED in _looked_up(result)


def test_a_module_that_searches_no_external_source_still_searches_memory(tmp_path):
    result = _run_with(PassThroughRetrieve(), tmp_path)

    assert REMEMBERED in _looked_up(result), (
        "原樣帶過 now means it searches no external source, not that it searches nothing"
    )


def test_keyword_lookup_reports_both_what_it_matched_and_what_it_remembered(tmp_path):
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=KeywordRetrieve(items=[{"keywords": ["鞋號"], "content": "鞋號表在櫃檯。"}]),
        action=DirectAnswerAction(),
    ).run("鞋號", memory=_memory_holding_something(tmp_path), session_id="now")

    looked_up = _looked_up(result)
    assert "鞋號表在櫃檯。" in looked_up, "its own source still answers"
    assert REMEMBERED in looked_up, "and memory answers alongside it"


def test_a_workflow_without_a_long_term_memory_behaves_as_before(tmp_path):
    result = Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=PassThroughRetrieve(),
        action=DirectAnswerAction(),
    ).run("鞋號")

    assert result.stop_reason == "end_turn", "nothing to search is not a failure"


def test_no_retrieve_module_is_told_where_the_memory_lives(tmp_path):
    import inspect

    for module in (PassThroughRetrieve, KeywordRetrieve, SemanticRetrieve):
        taken = set(inspect.signature(module.__init__).parameters)
        assert not taken & {"root", "memory", "memory_root", "store"}, (
            f"{module.__name__} would then have to be kept in step with the memory's own setting"
        )


def test_the_semantic_index_is_not_built_until_something_is_looked_up(tmp_path, monkeypatch):
    built: list[object] = []
    (tmp_path / "policy.md").write_text("保固兩年。", encoding="utf-8")

    class _CountedKnowledgeBase:
        def __init__(self, **_kwargs):
            built.append(self)

        def search(self, query, top_k=3):
            return []

    monkeypatch.setattr("agentic_sdk.modules.retrieve.semantic.FaissKnowledgeBase", _CountedKnowledgeBase)
    retrieve = SemanticRetrieve(sources=[str(tmp_path)], embedder=_AnEmbedder())

    assert built == [], "reading the sources costs a run that may never look anything up"

    Workflow(
        perceive=PassThroughPerceive(),
        plan=PassThroughPlan(),
        retrieve=retrieve,
        action=DirectAnswerAction(),
    ).run("保固")

    assert len(built) == 1, "the first lookup builds it"


def test_a_missing_embedder_is_caught_when_the_agent_is_wired_not_mid_answer(tmp_path):
    with pytest.raises(ValueError):
        SemanticRetrieve(sources=[str(tmp_path)])


def test_an_index_that_failed_to_build_fails_again_rather_than_finding_nothing(tmp_path, monkeypatch):
    def refuse(**_kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr("agentic_sdk.modules.retrieve.semantic.FaissKnowledgeBase", refuse)
    retrieve = SemanticRetrieve(sources=[str(tmp_path)], embedder=_AnEmbedder())

    for _ in range(2):
        with pytest.raises(RuntimeError):
            retrieve._ensure_knowledge_base()


class _AnEmbedder:
    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]

    def embed_many(self, texts):
        return [self.embed(text) for text in texts]
