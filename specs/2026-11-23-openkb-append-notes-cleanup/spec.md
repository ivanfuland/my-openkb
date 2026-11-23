---
spec: "2026-11-23-openkb-append-notes-cleanup"
version: "v1.0"
project: "my-openkb"
---

# Spec: Fix Append-Mode Multiline `## Notes` Cleanup, Progress Warning Counts, and Empty-Content Retry

## Problem

Production `nas-archive` ingest after upgrading to `openkb v0.1.dev182+ga4866febb` revealed two real defects in `openkb/agent/compiler.py` and `openkb/agent/compiler_notes.py`:

1. **Multiline `## Notes` duplicates on `recompile` / `remove`**:
   - `_upsert_note_line` (`openkb/agent/compiler_notes.py:125-129`) writes `note` verbatim without collapsing internal newlines, while both `_upsert_note_line` and `compiler.py:1676-1681` strip old entries with a single-line regex (`^- \*\*.*\(\[\[summaries/{doc_name}\]\]\)[ \t]*\n?` without multiline continuation matching).
   - When an LLM returns a multi-paragraph or multi-line `note`, re-ingesting or removing the document fails to remove the prior entry and leaves duplicate `## Notes` bullets for the same source document.
2. **Misleading `[WARN]` planned-vs-written counts and occasional empty-content failures**:
   - `compiler.py:2665-2672` (concepts) and `compiler.py:2696-2707` (entities) check `written + self_handled < total` (and `ewritten + entity_self_handled < etotal`) to decide whether a failure occurred, but print only `written` / `ewritten` instead of counting `self_handled` / `entity_self_handled` (buffered pending notes and promoted pages), making a 9/10 run look like 7/10.
   - Occasional transient `ValueError("LLM returned empty content ...")` on a single concept/entity generation immediately fails that topic without a bounded retry.

## Contract

1. Introduce a single shared `## Notes` entry removal helper used by both `compiler_notes._upsert_note_line` and `compiler.py`'s document-removal path (`_remove_doc_from_pages` / `remove_doc_from_concept_pages` / `remove_doc_from_entity_pages`):
   - Normalize newlines inside newly written notes in `_upsert_note_line` so future bullets are clean single-line Markdown bullets.
   - Remove both single-line and legacy multi-line `## Notes` entries belonging to `[[summaries/{doc_name}]]` (starting at `- **...` and ending with `([[summaries/{doc_name}]])`, without touching other documents' bullets or prose outside `## Notes`).
2. Fix both concept and entity `[WARN]` summary lines (`compiler.py:2665-2707`) to report total succeeded (`written + self_handled` / `ewritten + entity_self_handled`) while preserving the downstream-parsed `planned but only <N> written` prefix contract (optionally annotating staged/promoted counts in the parenthetical detail).
3. Add a bounded single retry (at most 1 retry) when a concept/entity/note generation raises the empty-content `ValueError` (never retrying `OSError` or `TruncatedResponseError`).
4. Add unit and integration tests covering all three behaviors.

## Non-goals

- Do not touch `.no-mistakes.yaml` or break `tests/test_file_size.py` (`openkb/config.py < 800` lines).
- Do not modify live KB files under `/home/ivan/.local/share/openkb/`.
