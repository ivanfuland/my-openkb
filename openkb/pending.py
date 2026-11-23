"""Pending-topic buffer for the wiki compiler (see issue #247).

The compiler uses this store to defer page creation for one-off topics.
Persistence follows ``openkb.state.HashRegistry``'s load-on-init and
persist-on-mutation pattern.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from openkb.locks import atomic_write_json

#: Number of distinct documents required in the buffer before a note from
#: another document triggers promotion. Intentionally fixed (see issue #247).
MAX_NOTES_BEFORE_PROMOTION = 2


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
            self._data: dict[str, dict[str, dict]] = data if isinstance(data, dict) else {}
        else:
            self._data = {}
        for kind in ("concepts", "entities"):
            for entry in self._data.setdefault(kind, {}).values():
                by_doc = {note["doc_name"]: note for note in entry.get("notes", [])}
                entry["notes"] = list(by_doc.values())

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
        }
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
