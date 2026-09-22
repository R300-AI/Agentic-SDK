from __future__ import annotations

import copy
import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from agentic_sdk.llm import chat_json, require_model, resolve_openai_client
from agentic_sdk.memory.in_memory import InMemoryStore
from agentic_sdk.memory.protocol import MemoryEntry


# Enough of the conversation is always left alone that the agent still knows
# what was just said, however tight the budget is.
_ALWAYS_KEEP_RECENT_TURNS = 2

# How alike two descriptions must read before one counts as already covering
# the other. Set where a shared subject beats shared wording: lower and
# unrelated topics merge, higher and the index collects a near-duplicate
# line on every pass.
_SAME_SUBJECT_OVERLAP = 0.6

_SYNTHESISE_SYSTEM_PROMPT = (
    "SYNTHESISE. You are given the oldest part of a conversation that no longer fits. "
    "Return JSON with two fields. "
    '"description": one line, at most about 150 characters, naming what this part was about, '
    "so that whoever reads a list of such lines can tell whether it is worth opening. "
    '"content": what happened in that part, in the language it was held in, keeping any fact '
    "a later exchange might depend on. Do not invent anything that was not said."
)


def estimate_tokens(text: str) -> int:
    """About how many tokens a piece of text costs.

    An OpenAI-compatible endpoint is not required to expose a tokenizer, and
    this SDK targets many of them, so the count here is an estimate and is
    named as one. A character in a CJK script is worth roughly a token; other
    scripts run about four characters to one. A deployment that needs the real
    number passes its own counter.
    """
    cjk = sum(1 for char in text if _is_dense_script(char))
    return cjk + (len(text) - cjk + 3) // 4


_UNSAFE_IN_A_FILE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _as_one_path_component(name: str) -> str:
    """One name, safe to use as a single directory or file name.

    Workflow names and entry ids both come from whoever built them, so either
    can hold separators that would put the memory somewhere else entirely.
    """
    cleaned = _UNSAFE_IN_A_FILE_NAME.sub("-", str(name)).strip("-.")
    return cleaned or "default"


def _as_file_stem(entry_id: str) -> str:
    """An entry id as a file name, without two ids becoming one file.

    Cleaning alone would collapse ``a b`` and ``a-b`` into the same name and
    the second entry would silently replace the first, so anything that is not
    already safe is named by its digest instead. The id itself is written into
    the front matter, so nothing depends on reading it back off the name.
    """
    raw = str(entry_id)
    safe = _as_one_path_component(raw)
    if safe == raw:
        return safe
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class FileMemoryStore(InMemoryStore):
    """What a workflow remembers, kept as files a person can read.

    One entry, one markdown file, under a directory named after the workflow —
    so every conversation of that workflow reads the same memory, which is what
    makes it cross-context rather than per-run. The front matter says what the
    entry is, where it came from and when; the body is the entry itself.

    Files rather than a database because of who the reader is: the person who
    set this agent up in the Playground needs to see what it remembers and
    delete the entry it got wrong, and a directory of markdown is something
    they can open. See ADR-0011.

    Two kinds of content are deliberately not written: attachments and
    embeddings. Both are large and neither is readable, and losing them
    silently would be worse than not carrying them, so an entry that had
    attachments records how many it had in its front matter.
    """

    FRONT_MATTER_FENCE = "---"

    def __init__(
        self,
        root: str,
        *,
        workflow_name: str = "default",
        workflow_id: str = "default",
        session_id: str = "default",
        raw_retention_seconds: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        compaction_threshold_tokens: int | None = None,
        count_tokens: Callable[[str], int] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.raw_retention_seconds = raw_retention_seconds
        # Synthesis needs a model of its own: collecting old exchanges into one
        # is a smaller job than answering, so a deployment can point it at a
        # smaller endpoint than the one the action uses.
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self.compaction_threshold_tokens = compaction_threshold_tokens
        self._count_tokens = count_tokens or estimate_tokens
        self._on_event = on_event
        # Fail here rather than on the first append halfway through a run: a
        # root that cannot be written is a deployment mistake, and the run that
        # discovers it has already answered somebody.
        self.root.mkdir(parents=True, exist_ok=True)
        # The base class sets the names first and empties the entries last, so
        # loading during its work would be wiped; load once it has finished.
        super().__init__(workflow_name=workflow_name, workflow_id=workflow_id, session_id=session_id)
        self._load()

    # --- which workflow's memory this is ----------------------------------

    @property
    def workflow_name(self) -> str:
        return self._workflow_name

    @workflow_name.setter
    def workflow_name(self, name: str) -> None:
        """Setting the name moves this store to that workflow's memory.

        The workflow's own name is authoritative — ``Workflow`` assigns it onto
        whatever memory it was handed, after that memory was built. Without
        reloading here, a store built with one name and run under another would
        hold the first workflow's entries while writing into the second one's
        directory.
        """
        changed = getattr(self, "_workflow_name", None) != name
        self._workflow_name = name
        if changed and hasattr(self, "_entries"):
            self._load()

    # --- where things live -------------------------------------------------

    @property
    def workflow_dir(self) -> Path:
        return self._dir_for_workflow(self.workflow_name)

    def _dir_for_workflow(self, workflow_name: str) -> Path:
        return self.root / _as_one_path_component(workflow_name)

    def _path_for(self, entry: MemoryEntry) -> Path:
        # An entry names the workflow it belongs to, and that is what decides
        # the directory — not whichever store happens to be writing it.
        return (
            self._dir_for_workflow(entry.workflow_name)
            / _as_one_path_component(entry.tier or "raw")
            / f"{_as_file_stem(entry.entry_id)}.md"
        )

    # --- reading and writing ----------------------------------------------

    def append(self, entry: MemoryEntry) -> None:
        """Every write path on the base class funnels through here."""
        super().append(entry)
        self._write(entry)

    def copy_for_run(self) -> "FileMemoryStore":
        """A copy for one run holds the same entries and writes to the same place.

        The entries are copied rather than re-read, for the same reason the
        base class copies them: re-reading would drop everything the files do
        not carry, and embeddings are not carried — a copy that quietly lost
        them would make every embedding search score nothing.
        """
        copied = FileMemoryStore(
            root=str(self.root),
            workflow_name=self.workflow_name,
            workflow_id=self.workflow_id,
            session_id=self.session_id,
            raw_retention_seconds=self.raw_retention_seconds,
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            compaction_threshold_tokens=self.compaction_threshold_tokens,
            count_tokens=self._count_tokens,
            on_event=self._on_event,
        )
        copied._entries = copy.deepcopy(self._entries)
        return copied

    # --- collecting the oldest of it into topics ---------------------------

    def tokens_in(self, messages: "list[dict[str, Any]] | str") -> int:
        """What this would cost to hand over."""
        if isinstance(messages, str):
            return self._count_tokens(messages)
        return sum(self._count_tokens(str(message.get("content", ""))) for message in messages)

    def index_lines(self) -> list[str]:
        """One line per topic, oldest first.

        Not stored anywhere: it is read off the topics every time, so it cannot
        drift away from what the topics actually say.
        """
        topics = sorted(
            (entry for entry in self._entries if entry.tier == "topic" and entry.description),
            key=lambda entry: entry.created_at,
        )
        return [entry.description for entry in topics]

    def as_openai_messages(self, *, include_attachments: bool = False) -> list[dict[str, Any]]:
        """The memory's exit, and so where it checks whether it still fits."""
        if self.compaction_threshold_tokens is not None:
            try:
                self.compact(self.compaction_threshold_tokens)
            except Exception:  # noqa: BLE001 - too much beats nothing at all
                if self._on_event is not None:
                    self._on_event({"type": "memory_compaction_failed"})
        return super().as_openai_messages(include_attachments=include_attachments)

    def compact(self, threshold_tokens: int) -> int:
        """Collect the oldest exchanges into topics until this fits again.

        Returns how many topics were made. Oldest first, because what was just
        said is what the next answer depends on. Nothing is deleted: the raw
        entries stay on disk and stay searchable, they simply stop being handed
        over as the conversation.
        """
        made = 0
        before = self.tokens_in(super().as_openai_messages())
        while before > threshold_tokens:
            covered = self._oldest_uncovered_exchanges()
            if len(covered) < 2:
                break
            self._synthesise(covered)
            made += 1
            after = self.tokens_in(super().as_openai_messages())
            if after >= before:
                # That pass gained nothing, so another will not either.
                # Handing over more than was asked for beats looping
                # against the endpoint.
                break
            before = after
        return made

    def _oldest_uncovered_exchanges(self) -> list[MemoryEntry]:
        live = [
            entry
            for entry in self._entries
            if entry.tier == "raw"
            and not entry.metadata.get("synthesised_into")
            and entry.role in {"user", "assistant", "tool"}
            and (entry.session_id is None or entry.session_id == self.session_id)
        ]
        live.sort(key=lambda entry: (entry.turn_index if entry.turn_index is not None else 10**9, entry.created_at))
        available = live[:-_ALWAYS_KEEP_RECENT_TURNS] if len(live) > _ALWAYS_KEEP_RECENT_TURNS else []
        if len(available) < 2:
            return []
        return available[: max(2, len(available) // 2)]

    def _synthesise(self, covered: list[MemoryEntry]) -> MemoryEntry:
        description, body = self._ask_for_a_topic(covered)
        existing = self._topic_already_covering(description)
        if existing is not None:
            # Updating a topic means synthesising it again over what it
            # already covered plus what is being added. Appending instead
            # would grow the topic every time, and the conversation would
            # never come back under the threshold that asked for this.
            description, body = self._ask_for_a_topic(
                covered, already_covered=existing.content
            )
            existing.content = body
            existing.description = description
            topic = existing
        else:
            topic = MemoryEntry(
                content=body,
                workflow_name=self.workflow_name,
                entry_type="conversation_turn",
                tier="topic",
                description=description,
                role="system",
                workflow_id=self.workflow_id,
                session_id=self.session_id,
                turn_index=covered[0].turn_index,
                created_at=covered[0].created_at,
            )
            super().append(topic)
        self._write(topic)

        for entry in covered:
            entry.metadata["synthesised_into"] = topic.entry_id
            self._write(entry)

        if self._on_event is not None:
            self._on_event(
                {
                    "type": "memory_compacted",
                    "collected": len(covered),
                    "topic_id": topic.entry_id,
                    "description": description,
                }
            )
        return topic

    def _topic_already_covering(self, description: str) -> "MemoryEntry | None":
        """An existing topic saying the same thing is updated, not joined by a second one.

        Otherwise the index grows a near-duplicate line every time, and the
        index is the part that sits in front of the model on every exchange.
        """
        wanted = _comparable_pieces(description)
        if not wanted:
            return None
        for entry in self._entries:
            if entry.tier != "topic" or not entry.description:
                continue
            if entry.session_id not in (None, self.session_id):
                # Another conversation's topic. Updating it would overwrite
                # what that conversation remembers, and this one's exchanges
                # would go under a topic it cannot even see.
                continue
            theirs = _comparable_pieces(entry.description)
            overlap = len(wanted & theirs) / max(1, len(wanted | theirs))
            if overlap >= _SAME_SUBJECT_OVERLAP:
                return entry
        return None

    def _ask_for_a_topic(
        self, covered: list[MemoryEntry], *, already_covered: str = ""
    ) -> "tuple[str, str]":
        client = resolve_openai_client("FileMemoryStore", api_key=self._api_key, base_url=self._base_url)
        transcript = "\n".join(str(entry.role) + ": " + str(entry.content) for entry in covered)
        if already_covered:
            transcript = "previously: " + already_covered + "\n" + transcript
        parsed = chat_json(
            client,
            model=require_model(self._model, "FileMemoryStore"),
            system=_SYNTHESISE_SYSTEM_PROMPT,
            user=transcript,
        ).as_json()
        description = str(parsed.get("description") or "").strip()
        body = str(parsed.get("content") or "").strip()
        return description, body or transcript

    def _conversation_turns(self):
        """What was collected into a topic stops being handed over as itself."""
        hidden = {entry.entry_id for entry in self._entries if entry.metadata.get("synthesised_into")}
        return [turn for turn in super()._conversation_turns() if turn.turn_id not in hidden]

    def _write(self, entry: MemoryEntry) -> None:
        path = self._path_for(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render(entry), encoding="utf-8")

    def _render(self, entry: MemoryEntry) -> str:
        fields: dict[str, Any] = {
            "entry_id": entry.entry_id,
            "entry_type": entry.entry_type,
            "tier": entry.tier,
            "created_at": entry.created_at,
            "workflow_id": entry.workflow_id,
            "session_id": entry.session_id,
            "description": entry.description,
        }
        if entry.role is not None:
            fields["role"] = entry.role
        if entry.turn_index is not None:
            fields["turn_index"] = entry.turn_index
        if entry.importance != 1.0:
            fields["importance"] = entry.importance
        if entry.attachments:
            fields["attachments_not_kept"] = len(entry.attachments)
        if entry.metadata:
            fields["metadata"] = entry.metadata
        front = yaml.safe_dump(fields, allow_unicode=True, sort_keys=True).rstrip("\n")
        fence = self.FRONT_MATTER_FENCE
        return f"{fence}\n{front}\n{fence}\n\n{entry.content}\n"

    def _load(self) -> None:
        entries: list[MemoryEntry] = []
        for path in sorted(self.workflow_dir.rglob("*.md")):
            entry = self._parse(path)
            if entry is None:
                continue
            if self._is_past_retention(entry):
                path.unlink(missing_ok=True)
                continue
            entries.append(entry)
        entries.sort(key=lambda e: (e.created_at, e.turn_index if e.turn_index is not None else 0))
        self._entries = entries

    def _is_past_retention(self, entry: MemoryEntry) -> bool:
        if self.raw_retention_seconds is None or entry.tier != "raw":
            return False
        return (time.time() - entry.created_at) > self.raw_retention_seconds

    def _parse(self, path: Path) -> MemoryEntry | None:
        """A file that is not one of ours is left alone rather than guessed at."""
        text = path.read_text(encoding="utf-8")
        fence = self.FRONT_MATTER_FENCE
        if not text.startswith(f"{fence}\n"):
            return None
        _, _, rest = text.partition(f"{fence}\n")
        front_text, fenced, body = rest.partition(f"\n{fence}\n")
        if not fenced:
            return None
        fields = yaml.safe_load(front_text) or {}
        if not isinstance(fields, dict):
            return None
        return MemoryEntry(
            content=body.strip("\n"),
            # The directory this came out of says which workflow it belongs to.
            workflow_name=self.workflow_name,
            entry_type=str(fields.get("entry_type", "memory")),
            tier=str(fields.get("tier", "raw")),
            description=str(fields.get("description") or ""),
            role=fields.get("role"),
            workflow_id=fields.get("workflow_id"),
            # A file with no conversation named is left unowned, the way the
            # base class reads it: visible to every conversation of this
            # workflow. Anything this store wrote names one.
            session_id=fields.get("session_id"),
            turn_index=fields.get("turn_index"),
            metadata=dict(fields.get("metadata") or {}),
            importance=float(fields.get("importance", 1.0)),
            entry_id=str(fields.get("entry_id") or path.stem),
            created_at=float(fields.get("created_at", 0.0)),
            last_accessed_at=float(fields.get("created_at", 0.0)),
        )

    def clear(self, workflow_name: str | None = None) -> None:
        """Forgetting means the files go too, or they come back on the next load."""
        going = [entry for entry in self._entries if workflow_name in (None, entry.workflow_name)]
        super().clear(workflow_name)
        for entry in going:
            self._path_for(entry).unlink(missing_ok=True)


def _is_dense_script(char: str) -> bool:
    """Scripts where one character carries about as much as one token."""
    return (
        "\u3000" <= char <= "\u9fff"
        or "\uac00" <= char <= "\ud7a3"
        or "\uff00" <= char <= "\uffef"
    )


def _comparable_pieces(text: str) -> set[str]:
    """Pieces of a line, for telling two descriptions apart.

    Splitting on spaces alone makes a Chinese sentence one single piece, so
    two descriptions about the same thing would never look alike and the
    index would collect a near-duplicate line every time. Dense scripts are
    compared by adjacent character pairs instead.
    """
    lowered = str(text).lower()
    pieces = {part for part in re.split(r"[\s\uff0c\u3002\u3001,.;\uff1b:\uff1a!\uff01?\uff1f]+", lowered) if part}
    dense = [char for char in lowered if _is_dense_script(char)]
    pieces |= {dense[index] + dense[index + 1] for index in range(len(dense) - 1)}
    return pieces
