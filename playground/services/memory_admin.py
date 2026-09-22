"""What a workflow remembers, for the person who has to look at it.

Reading and striking out, and nothing else. Editing is deliberately absent:
the reader here is somebody on the floor, not the person who wrote the agent,
and a topic's one-line description goes in front of the model every single
turn. An edited line that reads fine and says the wrong thing is worse than
no line at all, because nothing downstream will ever question it.
"""

from __future__ import annotations

from typing import Any

from agentic_sdk import FileMemoryStore

from playground.services.runner_service import memory_root


def remembered_by(workflow_name: str) -> list[dict[str, Any]]:
    """Everything this workflow remembers, oldest first.

    The same list the model is shown each turn, so the one somebody strikes out
    is the one that was wrong. An agent that carries nothing over, or that has
    not collected anything yet, remembers nothing and says so with an empty
    list rather than an error — there is nothing wrong with either.
    """
    return [
        {
            "id": topic.entry_id,
            "description": topic.description,
            "content": topic.content,
        }
        for topic in _memory_of(workflow_name).remembered_topics()
    ]


def forget(workflow_name: str, entry_id: str) -> None:
    """Strike one topic out, and stop it being made again.

    Raises ``LookupError`` when there is no such topic, rather than reporting
    success for something that did not happen: whoever struck it out is about
    to look at the list again.
    """
    _memory_of(workflow_name).forget_topic(entry_id)


def _memory_of(workflow_name: str) -> FileMemoryStore:
    # Not scoped to one conversation. Topics belong to the workflow, and
    # somebody reviewing what it remembers is reviewing all of it.
    return FileMemoryStore(root=str(memory_root()), workflow_name=workflow_name)
