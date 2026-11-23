---
ticket: "OKB-APPEND-NOTES-01"
title: "Fix multiline ## Notes cleanup/normalization, self_handled WARN counts, and bounded empty-content retry"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-append-notes-cleanup"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "openkb/agent/compiler_notes.py & openkb/agent/compiler.py: normalize newlines when writing ## Notes bullets and share one removal helper that strips both single-line and legacy multiline ## Notes entries for [[summaries/{doc_name}]] without disturbing sibling bullets or non-Notes content."
  - "openkb/agent/compiler.py: count self_handled/entity_self_handled in concept and entity [WARN] planned-vs-written messages (preserving the `planned but only N written` prefix format) and add a single bounded retry on empty-content ValueError in concept/entity/note generation."
  - "tests/: add focused regression tests covering multiline note normalization, legacy multiline note removal on upsert/recompile/remove, WARN count accounting with self_handled for concepts and entities, and empty-content bounded retry (succeeds on retry; still warns/fails when both attempts are empty)."
evidence:
  - "uv run --locked --extra dev --extra api --python 3.12 ruff check ., ruff format --check ., mypy openkb, pytest, and git diff --check."
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb && uv run --locked --extra dev --extra api --python 3.12 pytest && git diff --check"
    expect: "All lint, format, mypy, pytest checks (including test_file_size.py) and git diff --check pass; .no-mistakes.yaml is untouched."
allowed_paths:
  - "openkb/"
  - "tests/"
  - "specs/"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: "litellm-local-gpt/gpt-6.2-sol"
recommended_effort: "high"
rework_budget: 2
---

# Ticket: OKB-APPEND-NOTES-01

## Context

Read the diagnostic handoff report at `/home/ivan/.local/share/fm-homes/telemetry/data/openkb-studio-observation/post-pr-bundle-ingest-issues-2026-11-23.md` (Issues #2 and #3).

## Required Changes

1. **Multiline `## Notes` normalization & shared removal helper (`openkb/agent/compiler_notes.py`, `openkb/agent/compiler.py`)**:
   - In `compiler_notes._upsert_note_line`, collapse internal newlines in `note` into clean single-line text before formatting `- **{date}** {note} ([[summaries/{doc_name}]])` so newly appended notes never break Markdown bullet structure.
   - Define one shared helper (e.g. in `compiler_notes.py`, reused by both `_upsert_note_line` and `compiler.py:1676` in `_remove_doc_from_pages`) that strips any `## Notes` bullet entry belonging to `[[summaries/{doc_name}]]`, whether single-line OR legacy multi-line (an entry starting with `- **` followed by continuation lines that do not start a new `- **` bullet or markdown heading `#`, ending with `([[summaries/{doc_name}]])`).
   - Scope removal carefully so bullets for other documents, prose outside `## Notes`, and surrounding headings/spacing remain intact.
   - Check `openkb/agent/consolidator.py` as well to ensure note counting/splitting handles legacy multiline notes cleanly if applicable.

2. **Accurate `[WARN]` counts with `self_handled` (`openkb/agent/compiler.py:2665-2707`)**:
   - For both concepts (`written + self_handled < total`) and entities (`ewritten + entity_self_handled < etotal`), report `handled = written + self_handled` (and `ehandled = ewritten + entity_self_handled`) in the `[WARN]` stdout line while keeping the `planned but only {handled} written` wording parsed by downstream callers (e.g., if `self_handled > 0`, include breakdown inside the trailing parentheses such as `({written} direct, {self_handled} staged/promoted; {reason})`).

3. **Bounded single retry on empty-content `ValueError` (`openkb/agent/compiler.py`)**:
   - When a concept/entity/note generation call returns empty content (`_require_nonempty_content` raises `ValueError`), retry the LLM call at most once before letting the `ValueError` propagate.
   - Never retry `OSError` or `TruncatedResponseError`.

4. **Tests**:
   - Add unit/integration tests covering:
     - Writing a multiline note normalizes it to a single-line bullet.
     - Re-upserting (`_upsert_note_line`) and removing (`remove_doc_from_concept_pages` / `remove_doc_from_entity_pages` / `openkb remove`) cleanly strip both single-line and legacy multiline `## Notes` entries for the target document without harming other bullets or non-Notes content.
     - `[WARN]` lines for both concepts and entities accurately count `written + self_handled` while keeping `planned but only <N> written`.
     - Empty-content generation retries once and succeeds when the second attempt returns valid content, and fails/warns once when both attempts return empty content (without retrying `TruncatedResponseError`).
