"""Declaring which memory a workflow keeps, alongside its modules.

Memory is not a module: it has no slot in the walk, it is what every module
reads from and writes to. It is declared the way modules are — a kind and its
settings — because that is the shape somebody already knows how to write, but
it sits in its own field rather than among the five.

Observed at ``build_workflow()``: give it a config and look at the memory the
workflow came out holding.
"""

from __future__ import annotations

from agentic_sdk import (
    FileMemoryStore,
    InContextMemory,
    InMemoryStore,
    MemorySpec,
    WorkflowConfig,
    build_workflow,
)


def test_a_workflow_that_declares_nothing_keeps_only_this_conversation():
    workflow = build_workflow(WorkflowConfig())

    assert workflow.memory_type is InContextMemory, (
        "carrying nothing between conversations is the smaller promise, so it is the default"
    )


def test_a_workflow_can_declare_that_it_carries_things_between_conversations(tmp_path):
    config = WorkflowConfig(memory=MemorySpec(kind="cross_context", params={"root": str(tmp_path)}))

    memory = build_workflow(config).memory_type

    assert isinstance(memory, FileMemoryStore), "somewhere to keep it means it is kept there"
    assert memory.root == tmp_path


def test_cross_context_memory_with_nowhere_to_keep_it_keeps_it_in_memory():
    memory = build_workflow(WorkflowConfig(memory=MemorySpec(kind="cross_context"))).memory_type

    assert isinstance(memory, InMemoryStore), (
        "the kind names what the memory does, so a deployment that has said nothing about "
        "where things live still gets a workflow that runs"
    )


def test_the_kind_names_what_the_memory_does_and_not_where_it_writes(tmp_path):
    config = WorkflowConfig(memory=MemorySpec(kind="cross_context", params={"root": str(tmp_path)}))

    assert config.memory.kind == "cross_context", (
        "a spec somebody saved must not have to be rewritten because the SDK changed "
        "what it writes to"
    )


def test_the_endpoint_synthesis_uses_is_part_of_what_is_declared(tmp_path):
    config = WorkflowConfig(
        memory=MemorySpec(
            kind="cross_context",
            params={
                "root": str(tmp_path),
                "api_key": "test-key",
                "base_url": "https://example.openai.test/v1",
                "model": "foundry-openai-like",
                "compaction_threshold_tokens": 1200,
            },
        )
    )

    memory = build_workflow(config).memory_type

    assert memory._model == "foundry-openai-like", (
        "collecting old exchanges into a topic is a model call, so the memory needs an endpoint"
    )
    assert memory.compaction_threshold_tokens == 1200


def test_a_setting_the_memory_does_not_take_is_refused_by_name(tmp_path):
    config = WorkflowConfig(memory=MemorySpec(kind="cross_context", params={"root": str(tmp_path), "colour": "red"}))

    try:
        build_workflow(config)
    except ValueError as error:
        assert "colour" in str(error), "the name of what was refused is what the person has to fix"
        assert "root" in str(error), "and what it would have accepted is the rest of the fix"
    else:
        raise AssertionError("a setting nobody can act on must not be accepted in silence")


def test_an_unknown_kind_is_refused_by_name():
    try:
        build_workflow(WorkflowConfig(memory=MemorySpec(kind="vector_db")))
    except ValueError as error:
        assert "vector_db" in str(error)
        assert "cross_context" in str(error), "and the kinds there are"
    else:
        raise AssertionError("an unknown kind must not silently become the default one")


def test_memory_is_not_one_of_the_five_modules():
    config = WorkflowConfig(memory=MemorySpec(kind="in_context"))

    assert "memory" not in config.modules, (
        "the walk visits five modules; a sixth entry here would be a module the workflow "
        "never visits"
    )
