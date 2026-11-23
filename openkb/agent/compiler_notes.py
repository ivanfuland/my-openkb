"""Append-only note ingest for OpenKB's wiki compiler (``concept_update_mode="append"``).

Companion to ``openkb.agent.compiler``: instead of sending an existing concept/
entity page's full body back to the LLM for a rewrite (``_gen_update``/
``_gen_entity_update`` in ``compiler.py``), this module generates a short note
about the new document — the LLM never sees the existing page — and appends
it deterministically (no LLM call for the write itself) as a dated,
source-linked entry under a ``## Notes`` heading in the same page. See
``openkb.agent.consolidator`` for the separate prose rewrite.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

from openkb import frontmatter
from openkb.locks import atomic_write_text

logger = logging.getLogger(__name__)

_NOTES_HEADING = "## Notes"
_NOTE_BULLET = "- **"
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
_NOTE_SOURCE_SUFFIX = re.compile(r"\(\[\[summaries/([^\]]+)\]\]\)[ \t]*$")

# ---------------------------------------------------------------------------
# Prompt templates — deliberately slim: no existing page content, no wikilink
# whitelist (notes stay plain text; see module docstring / SKILL.md for why).
# ---------------------------------------------------------------------------

_CONCEPT_NOTE_CREATE_USER = """\
This is a NEW concept page: {title}

This concept was just identified in document "{doc_name}" (summarized above).
{extra_context}

Return a JSON object with two keys:
- "description": A single sentence (under 100 chars) defining this concept
- "note": Some short sentences (or just a few keywords if that's enough) \
capturing what THIS document says about {title} — it will be appended to a \
running list of notes, not written as prose. Do NOT use [[wikilinks]].

Return ONLY valid JSON, no fences.
"""

_CONCEPT_NOTE_UPDATE_USER = """\
Concept page: {title}

Document "{doc_name}" (summarized above) mentions this concept.

Return a JSON object with one key:
- "note": Some short sentences (or just a few keywords if that's enough) \
capturing what THIS document adds about {title} — it will be appended to a \
running list of notes, not merged into the existing page (which you do not \
see). Do NOT use [[wikilinks]].

Return ONLY valid JSON, no fences.
"""

_ENTITY_NOTE_CREATE_USER = """\
This is a NEW entity page: {title} (type: {type})

This entity was just identified in document "{doc_name}" (summarized above).
{extra_context}

Return a JSON object with two keys:
- "description": A single sentence (under 100 chars) identifying this entity
- "note": Some short sentences (or just a few keywords if that's enough) \
capturing what THIS document says about {title} — it will be appended to a \
running list of notes, not written as prose. Do NOT use [[wikilinks]].

Return ONLY valid JSON, no fences.
"""

_ENTITY_NOTE_UPDATE_USER = """\
Entity page: {title} (type: {type})

Document "{doc_name}" (summarized above) mentions this entity.

Return a JSON object with one key:
- "note": Some short sentences (or just a few keywords if that's enough) \
capturing what THIS document adds about {title} — it will be appended to a \
running list of notes, not merged into the existing page (which you do not \
see). Do NOT use [[wikilinks]].

Return ONLY valid JSON, no fences.
"""


def note_fields(raw: str) -> tuple[str, str]:
    """Map a note LLM response to ``(description, note)``.

    Mirrors ``compiler._page_fields`` for the smaller note shape: not-JSON
    responses fall back to using the raw text as the note itself (a model
    that ignores the JSON instruction still produces a usable short note).
    """
    from openkb.agent import compiler as _compiler  # local: avoid import cycle

    try:
        obj = _compiler._parse_page_json(raw)
    except (json.JSONDecodeError, ValueError):
        return "", raw.strip()
    if obj is None:
        return "", ""
    note = obj.get("note")
    return frontmatter.single_line_description(obj.get("description")), (
        note.strip() if isinstance(note, str) else ""
    )


def _notes_section_bounds(
    lines: list[str], heading: str = _NOTES_HEADING
) -> Iterator[tuple[int, int]]:
    """Yield the heading index and exclusive end of each Notes section."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            if start is not None:
                yield start, i
            start = i
        elif start is not None and _ATX_HEADING.match(line.rstrip("\r\n")):
            yield start, i
            start = None
    if start is not None:
        yield start, len(lines)


def remove_doc_notes(body: str, doc_name: str, heading: str = _NOTES_HEADING) -> str:
    """Remove this source's dated bullets and their legacy continuation lines."""
    lines = body.splitlines(keepends=True)
    kept: list[str] = []
    kept_from = 0
    for start, end in _notes_section_bounds(lines, heading):
        note_start = None
        for i in range(start + 1, end):
            line = lines[i]
            if line.lstrip().startswith(_NOTE_BULLET):
                note_start = i
            if note_start is None:
                continue
            marker = _NOTE_SOURCE_SUFFIX.search(line.rstrip("\r\n"))
            if marker is None:
                continue
            if marker[1] == doc_name:
                kept.extend(lines[kept_from:note_start])
                kept_from = i + 1
            # A source suffix closes the bullet, even for a different doc.
            note_start = None
    kept.extend(lines[kept_from:])
    return "".join(kept)


def _upsert_note_line(
    body: str, doc_name: str, note: str, heading: str = _NOTES_HEADING, *, date: str | None = None
) -> str:
    """Replace the source's notes with one single-line entry, newest first."""
    marker = f"[[summaries/{doc_name}]]"
    date = date or datetime.date.today().isoformat()
    note = " ".join(part for line in note.splitlines() if (part := line.strip()))
    line = f"- **{date}** {note} ({marker})"

    lines = remove_doc_notes(body, doc_name, heading).split("\n")
    section = next(_notes_section_bounds(lines, heading), None)
    if section is None:
        while lines and lines[-1].strip() == "":
            lines.pop()
        if lines:
            lines.append("")
        lines.append(heading)
        lines.append("")
        lines.append(line)
    else:
        insert_at = section[0] + 1
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        lines.insert(insert_at, line)

    return "\n".join(lines)


def _build_frontmatter(fm_lines: list[str]) -> str:
    """Build a fresh frontmatter block (delimiters + trailing blank line)."""
    return "---\n" + "\n".join(fm_lines) + "\n---\n\n"


def append_concept_note(
    wiki_dir: Path,
    name: str,
    note: str,
    source_file: str,
    doc_name: str,
    description: str = "",
) -> None:
    """Append a short note about ``doc_name`` to a concept page (no LLM write).

    Creates the page (with ``description`` in its frontmatter, if given) when
    it doesn't exist yet; on an existing page, only ``sources:`` is updated
    and a note line is upserted — ``description`` is never touched once set.
    """
    from openkb.agent import compiler as _compiler  # local: avoid import cycle

    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _compiler._sanitize_concept_name(name)
    path = (concepts_dir / f"{safe_name}.md").resolve()
    if not path.is_relative_to(concepts_dir.resolve()):
        logger.warning("Concept name escapes concepts dir: %s", name)
        return

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if source_file not in existing:
            existing = _compiler._prepend_source_to_frontmatter(existing, source_file)
        parts = frontmatter.split(existing)
        if parts is not None:
            fm_block, body = parts
            new_body = _upsert_note_line(body.lstrip("\n"), doc_name, note)
            atomic_write_text(path, fm_block + "\n" + new_body)
        else:
            # Malformed/absent frontmatter: rebuild rather than write a bare
            # body (mirrors compiler._write_concept's recovery path).
            fm_block = _build_frontmatter(
                [
                    frontmatter.kv_line("type", "Concept"),
                    frontmatter.list_line("sources", [source_file]),
                ]
            )
            new_body = _upsert_note_line(existing, doc_name, note)
            atomic_write_text(path, fm_block + new_body)
        return

    fm_lines = [
        frontmatter.kv_line("type", "Concept"),
        frontmatter.list_line("sources", [source_file]),
    ]
    if description:
        fm_lines.append(frontmatter.kv_line("description", description))
    body = _upsert_note_line(f"{_NOTES_HEADING}\n\n", doc_name, note)
    atomic_write_text(path, _build_frontmatter(fm_lines) + body)


def append_entity_note(
    wiki_dir: Path,
    name: str,
    note: str,
    source_file: str,
    doc_name: str,
    description: str = "",
    type_: str = "other",
) -> None:
    """Append a short note about ``doc_name`` to an entity page (no LLM write).

    Mirrors :func:`append_concept_note`; ``type_`` is only used to seed a new
    page's frontmatter (no re-classification on update, unlike the rewrite
    path's ``_gen_entity_update``) — a deliberate scope simplification for the
    append mode.
    """
    from openkb.agent import compiler as _compiler  # local: avoid import cycle

    entities_dir = wiki_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _compiler._sanitize_concept_name(name)
    path = (entities_dir / f"{safe_name}.md").resolve()
    if not path.is_relative_to(entities_dir.resolve()):
        logger.warning("Entity name escapes entities dir: %s", name)
        return

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if source_file not in existing:
            existing = _compiler._prepend_source_to_frontmatter(existing, source_file)
        parts = frontmatter.split(existing)
        if parts is not None:
            fm_block, body = parts
            new_body = _upsert_note_line(body.lstrip("\n"), doc_name, note)
            atomic_write_text(path, fm_block + "\n" + new_body)
        else:
            fm_block = _build_frontmatter(
                [
                    frontmatter.list_line("sources", [source_file]),
                    frontmatter.kv_line("type", (type_ or "other").title()),
                ]
            )
            new_body = _upsert_note_line(existing, doc_name, note)
            atomic_write_text(path, fm_block + new_body)
        return

    fm_lines = [
        frontmatter.list_line("sources", [source_file]),
        frontmatter.kv_line("type", (type_ or "other").title()),
    ]
    if description:
        fm_lines.append(frontmatter.kv_line("description", description))
    body = _upsert_note_line(f"{_NOTES_HEADING}\n\n", doc_name, note)
    atomic_write_text(path, _build_frontmatter(fm_lines) + body)
