"""Pending-topic buffer for the wiki compiler (see issue #247).

The compiler uses this store to defer page creation for one-off topics.
Persistence follows ``openkb.state.HashRegistry``'s load-on-init and
persist-on-mutation pattern.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from openkb.frontmatter import single_line_description
from openkb.locks import atomic_write_json

#: Number of distinct documents required in the buffer before a note from
#: another document triggers promotion. Intentionally fixed (see issue #247).
MAX_NOTES_BEFORE_PROMOTION = 2


_TOPIC_KINDS = ("concepts", "entities")


def pending_topics_path(kb_dir: Path) -> Path:
    return kb_dir / ".openkb" / "pending_topics.json"


class PendingTopicsStore:
    """Persistent buffer of not-yet-paged concept/entity candidates.

    Persisted as ``kb_dir/.openkb/pending_topics.json`` (same directory
    convention as ``state.HashRegistry``'s ``hashes.json``). Callers already
    hold the KB's exclusive lock (``@_with_kb_lock`` wraps every `add`/
    `add-all` run in ``cli.py``), so no additional locking is needed here.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError(f"{path}: pending topics must be a JSON object")
            self._data: dict[str, dict[str, dict]] = data
        else:
            self._data = {}
        for kind in _TOPIC_KINDS:
            topics = self._data.setdefault(kind, {})
            if not isinstance(topics, dict):
                raise ValueError(f"{path}: pending {kind} must be a JSON object")
            for entry in topics.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("notes", []), list):
                    raise ValueError(f"{path}: invalid pending {kind} entry")
                by_doc: dict[str, dict] = {}
                for note in entry.get("notes", []):
                    if not isinstance(note, dict) or not all(
                        isinstance(note.get(field), str)
                        for field in ("doc_name", "source_file", "note")
                    ):
                        raise ValueError(f"{path}: invalid pending {kind} note")
                    doc = note["doc_name"]
                    if not doc or doc in {".", ".."} or "/" in doc or "\\" in doc:
                        raise ValueError(f"{path}: invalid pending document name {doc!r}")
                    by_doc[doc] = note
                entry["notes"] = list(by_doc.values())

    def document_names(self) -> set[str]:
        """Earlier summaries that a promotion may need to backlink."""
        return {note["doc_name"] for note in self._all_notes()}

    def count_document_notes(self, doc_name: str) -> int:
        return sum(note["doc_name"] == doc_name for note in self._all_notes())

    def _all_notes(self):
        for kind in _TOPIC_KINDS:
            for entry in self._data[kind].values():
                yield from entry["notes"]

    def get(self, kind: str, slug: str) -> dict | None:
        """Return the pending entry for ``slug`` in ``kind``, or None."""
        return self._data[kind].get(slug)

    def notes(self, kind: str, slug: str, *, excluding_doc: str | None = None) -> list[dict]:
        entry = self.get(kind, slug)
        if entry is None:
            return []
        return [note for note in entry["notes"] if note["doc_name"] != excluding_doc]

    def note_count(self, kind: str, slug: str, *, excluding_doc: str | None = None) -> int:
        """Return how many notes are already buffered for ``slug`` (0 if absent)."""
        return len(self.notes(kind, slug, excluding_doc=excluding_doc))

    def add_note(
        self,
        kind: str,
        slug: str,
        description: str,
        doc_name: str,
        source_file: str,
        note: str,
        type_: str | None = None,
    ) -> int:
        """Store a note for ``doc_name`` within ``slug``, replacing any prior note.

        ``description`` is the LLM-generated one-sentence brief for this note
        (same value a real page's frontmatter ``description`` would get) —
        always overwritten with the latest call's value, not accumulated as a
        list, so it reflects the most recent summary of the topic across all
        buffered notes so far.

        Returns the new total note count (callers promote once this reaches
        ``MAX_NOTES_BEFORE_PROMOTION + 1``, i.e. the 3rd note).
        """
        entry = self._data[kind].setdefault(slug, {"description": description, "notes": []})
        entry["description"] = description
        if type_ is not None:
            entry["type"] = type_
        notes = entry["notes"]
        new_note = {
            "doc_name": doc_name,
            "source_file": source_file,
            "note": note,
            "date": datetime.date.today().isoformat(),
            "description": description,
        }
        if type_ is not None:
            new_note["type"] = type_
        for i, buffered in enumerate(notes):
            if buffered["doc_name"] == doc_name:
                notes[i] = new_note
                break
        else:
            notes.append(new_note)
        self._persist()
        return len(notes)

    def remove(self, kind: str, slug: str) -> None:
        """Remove a pending entry after the promoted page is fully written.

        Keeping the notes until then preserves the source material if a write
        or page-generation call fails. See ``test_promotion_failure_preserves_buffer``
        in ``tests/test_compiler.py``.
        """
        if slug in self._data[kind]:
            del self._data[kind][slug]
            self._persist()

    def remove_document(self, doc_name: str) -> int:
        """Purge a document's notes in both namespaces and prune empty topics."""
        removed = 0
        for kind in _TOPIC_KINDS:
            topics = self._data[kind]
            for slug, entry in list(topics.items()):
                notes = entry["notes"]
                surviving = [note for note in notes if note["doc_name"] != doc_name]
                if len(surviving) == len(notes):
                    continue
                removed += len(notes) - len(surviving)
                if not surviving:
                    del topics[slug]
                    continue
                entry["notes"] = surviving
                # Legacy notes lack per-document metadata. Use surviving text
                # as a brief instead of carrying forward the removed brief.
                latest = surviving[-1]
                entry["description"] = (
                    single_line_description(latest.get("description"))
                    or (" ".join(latest["note"].split())[:100])
                )
                if kind == "entities":
                    entry["type"] = latest.get("type", "other")
        if removed:
            self._persist()
        return removed

    def brief_lines(self, kind: str) -> list[str]:
        """Return ``- {slug} (pending, {n}/{total} mentions) — {description}`` lines.

        Pending briefs help the planner recognize topics it has already seen.
        The caller decides which topics are ready to become wikilink targets.
        A missing ``description`` indicates a malformed entry and raises
        ``KeyError``.
        """
        total = MAX_NOTES_BEFORE_PROMOTION + 1
        lines: list[str] = []
        for slug, entry in self._data[kind].items():
            notes = entry.get("notes", [])
            lines.append(
                f"- {slug} (pending, {len(notes)}/{total} mentions) — {entry['description']}"
            )
        return lines

    def _persist(self) -> None:
        atomic_write_json(self._path, self._data)
