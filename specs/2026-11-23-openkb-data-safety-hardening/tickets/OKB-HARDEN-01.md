---
ticket: "OKB-HARDEN-01"
title: "Fix my-openkb P0 truncation/corruption/rollback/promotion hazards, key P1 bugs, and add end-to-end integration tests"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-data-safety-hardening"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "openkb/agent/consolidator.py, openkb/agent/compiler.py, openkb/frontmatter.py: guard consolidate_page and summary-rewrite against finish_reason=length truncation, validate frontmatter before/after rewrite, check non-empty body AFTER stripping frontmatter, handle multiline YAML description safely, and sync consolidated description to wiki/index.md."
  - "openkb/add_coordinator.py, openkb/mutation.py, openkb/pending.py, openkb/cli.py: include pending_topics.json in add rollback/recovery journals (including absent-file case), assemble promoted pages in memory before atomic write, purge removed documents from pending_topics.json during openkb remove, backfill earlier summary backlinks on promotion, and exit non-zero from openkb consolidate when any page fails while preserving [OK]/[SKIP]/[ERROR] line formats."
  - "openkb/lint.py: align fix_broken_links with find_broken_links so valid bare-stem links (including in explorations/) are not stripped."
  - "tests/: add end-to-end CLI+filesystem integration tests covering truncation/corruption rejection, add rollback with pending_topics.json, mid-promotion failure, remove->pending purge->promote->consolidate->lint round trip, and non-zero failure exit code."
evidence:
  - "uv run --locked --extra dev --extra api --python 3.12 ruff check ., ruff format --check ., mypy openkb, pytest (all existing + new integration tests, including tests/test_file_size.py), and git diff --check."
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb && uv run --locked --extra dev --extra api --python 3.12 pytest && git diff --check"
    expect: "All lint, format, mypy, pytest checks (including file size limit <800 on openkb/config.py) and git diff --check pass; .no-mistakes.yaml is untouched."
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

# Ticket: OKB-HARDEN-01

## Context

Read the full audit report at `/home/ivan/.local/share/fm/data/as-c21c79f2d1bfa095fc03e52e/report.md` (exact `file:line` references and reproductions for every item below).

## Required Changes

1. **P0.1 — Truncation guards**:
   - In `openkb/agent/consolidator.py:consolidate_page`, route the LLM call through `_compiler._llm_call_page_async` (which passes `raise_on_truncation=True`) so `finish_reason="length"` aborts before writing even if JSON repair could parse a prefix.
   - In `openkb/agent/compiler.py`, guard `summary-rewrite` (v2 summary) against `finish_reason="length"` truncation by falling back cleanly to the intact v1 summary instead of persisting truncated v2 output.

2. **P0.2 — Consolidation & frontmatter write safety**:
   - In `openkb/agent/consolidator.py` and `openkb/frontmatter.py`:
     - Validate existing YAML frontmatter before calling the LLM; fail cleanly instead of writing back malformed YAML.
     - Strip any model-returned frontmatter fence BEFORE running `_require_nonempty_content`, so `{"content":"---\nfoo: bar\n---"}` raises instead of blanking the page.
     - Reject non-object JSON scalars (e.g. `false`) on destructive page rewrites.
     - Validate `description` is a plain single-line string (ignoring/rejecting non-strings like dicts/lists so YAML is never corrupted) and update `frontmatter.set_line` to replace multiline YAML block scalars (e.g. `description: |` + indented continuation lines) cleanly without leaving orphaned continuation lines that break YAML parsing.
     - Verify final serialized output has valid frontmatter and non-empty body before `atomic_write_text`.

3. **P0.3 — `pending_topics.json` in `add` rollback/journal**:
   - Include `.openkb/pending_topics.json` in the `add` mutation snapshot/journal (`openkb/add_coordinator.py`, `openkb/mutation.py`, and cloud-import snapshot path in `openkb/cli.py`), properly handling the absent-before-add case (deleting the newly created file on rollback) as well as restoring prior JSON bytes on rollback after failed promotion.

4. **P0.4 — Atomic promotion assembly**:
   - In `openkb/agent/compiler.py`, assemble and validate the complete promoted page (all buffered notes + current doc note + valid frontmatter + ghost-link sanitization) in memory BEFORE writing the page file to disk, so an `OSError` mid-promotion cannot leave a partial 1-note page on disk while `pending_topics.json` still holds the unpromoted buffer.

5. **Key P1 fixes**:
   - **`remove` purges `pending_topics.json`**: Add per-document removal to `openkb/pending.py` (removing entries for the removed summary from both `concepts` and `entities` and pruning empty topics), wire it into `openkb/cli.py:remove` (including preview and rollback/mutation bookkeeping).
   - **Promotion backlinks**: On promotion of a pending topic, add reverse links to earlier buffered summaries (not only current `doc_name`), snapshotting touched summaries in the mutation journal.
   - **Consolidate index sync & non-zero exit on failure**: Sync updated `description` to `wiki/index.md` on successful consolidation; track `failed` separately from `skipped` in `openkb/cli.py:consolidate()`, keep `[OK]`, `[SKIP]`, `[ERROR]`, and `Would consolidate ...` line formats compatible with downstream parsers, and exit non-zero (`ctx.exit(1)` or `sys.exit(1)`) when `failed > 0` (update `tests/test_consolidate_cli.py` expectations accordingly).
   - **`fix_broken_links` parity**: In `openkb/lint.py`, align `fix_broken_links` with `find_broken_links` so valid bare-stem links (e.g., `[[alpha]]` in `explorations/`) that `find_broken_links` treats as valid are preserved rather than stripped.

6. **End-to-End Integration Tests (`tests/`)**:
   - Add real Click + filesystem + compiler/coordinator/consolidator integration tests covering every P0 and P1 fix above (see Integration Test Plan items 1–4 in `/home/ivan/.local/share/fm/data/as-c21c79f2d1bfa095fc03e52e/report.md`).

## Out of Scope

- Do not touch `.no-mistakes.yaml`.
- Keep `openkb/config.py` strictly under 800 lines.
