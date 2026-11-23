"""Pending-topic buffer for the wiki compiler (see issue #247).

Buffers up to :data:`MAX_NOTES_BEFORE_PROMOTION` short notes per brand-new
concept/entity candidate before a dedicated wiki page is created, so a topic
mentioned exactly once or twice (a document's own ticket/case identifier, a
person mentioned only in passing) doesn't immediately get its own low-value
page — while a topic that genuinely recurs still gets promoted to a real
page, with all buffered notes as its starting content/sources. Used by
``openkb.agent.compiler``; kept as its own module so the JSON-backed
persistence mirrors ``openkb.state.HashRegistry``'s load-on-init /
persist-on-mutation pattern without growing that module further.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from openkb.locks import atomic_write_json

#: Number of notes collected before the NEXT note promotes the topic to a
#: real page (i.e. the 3rd mention creates the page). Intentionally not a
#: config key (see issue #247) — internal, hardcoded constant.
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
        """Remove a pending entry (called right after promotion to a real page)."""
        if slug in self._data[kind]:
            del self._data[kind][slug]
            self._persist()

    def brief_lines(self, kind: str) -> list[str]:
        """Return ``- {slug} (pending, {n}/{total} mentions) — {description}`` lines.

        Extends the plan call's existing-page briefs so the LLM treats
        pending topics like quasi-existing pages for dedup ("prefer update"/
        "related" over proposing a near-duplicate create). Pending slugs
        must NEVER be added to the wikilink whitelist (no real page exists
        yet) — enforcing that is the caller's responsibility, not this
        method's.

        ``entry["description"]`` is read directly (no fallback): every entry
        is guaranteed to have one, either from ``add_note`` or from the
        one-time migration of legacy entries that predate this field (see
        issue #247 follow-up) — a missing field is a genuine data bug, so it
        raises a plain ``KeyError`` rather than degrading silently.
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
