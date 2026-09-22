from __future__ import annotations

import copy
import hashlib
import re
import time
from pathlib import Path
from typing import Any

import yaml

from agentic_sdk.memory.in_memory import InMemoryStore
from agentic_sdk.memory.protocol import MemoryEntry


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
    ) -> None:
        self.root = Path(root)
        self.raw_retention_seconds = raw_retention_seconds
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
        )
        copied._entries = copy.deepcopy(self._entries)
        return copied

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
