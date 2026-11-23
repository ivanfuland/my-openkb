---
spec: "2026-11-23-openkb-data-safety-hardening"
version: "v1.0"
project: "my-openkb"
---

# Spec: Batch A — OpenKB Data Safety, Rollback Integrity, Consolidation Guards, and End-to-End Integration Tests

- Spec ID: `2026-11-23-openkb-data-safety-hardening`
- Spec Version: `v1.0`
- Project: `my-openkb`
- Base Branch: `main`

## Goal

Close all four verified P0 data-loss / silent-corruption hazards and the highest-impact P1 contract bugs identified in the `OKB-AUDIT-01` audit report (`/home/ivan/.local/share/fm/data/as-c21c79f2d1bfa095fc03e52e/report.md`), backed by real end-to-end integration tests exercising Click CLI + filesystem + mutation coordinator + compiler + consolidator.

## Scope

1. **P0.1 — Truncation protection (`openkb/agent/consolidator.py`, `openkb/agent/compiler.py`)**:
   - Switch `consolidator.consolidate_page` from unprotected `_llm_call_async` to `_llm_call_page_async` (passing `raise_on_truncation=True`) so `finish_reason="length"` (whether incomplete or syntactically valid JSON) raises and leaves the original page byte-identical.
   - Protect `summary-rewrite` (v2 summary) against `finish_reason="length"` truncation by falling back to the intact v1 summary rather than overwriting it with truncated v2 output.

2. **P0.2 — Safe consolidation & rewrite validation (`openkb/agent/consolidator.py`, `openkb/frontmatter.py`, `openkb/agent/compiler.py`)**:
   - Validate existing frontmatter before calling the LLM; reject malformed YAML instead of silently falling back to `{}`.
   - Strip any model-emitted frontmatter block BEFORE checking non-empty body (`_require_nonempty_content`), so `{"content":"---\nfoo: bar\n---"}` raises and never blanks a page.
   - Validate `description` is a plain single-line string (reject mappings/lists/non-strings or retain existing valid description) and handle multiline YAML `description: |` cleanly in `frontmatter.set_line` without corrupting subsequent indented continuation lines.
   - Reject non-object JSON scalars (e.g. `false`) and verify the final serialized page parses cleanly with valid YAML frontmatter and non-empty body before atomic replacement.

3. **P0.3 — Include `pending_topics.json` in `add` mutation rollback & recovery (`openkb/add_coordinator.py`, `openkb/mutation.py`, `openkb/cli.py`)**:
   - Include `.openkb/pending_topics.json` (including the absent-before-add case) in the add mutation snapshot/journal (both standard `add` and cloud import snapshot selector) so an interrupted or failed `add` restores `pending_topics.json` to its exact pre-attempt state—neither losing prior docs' buffered notes on failed promotion nor retaining orphan notes from a failed below-threshold ingest.

4. **P0.4 — Atomic promotion publication (`openkb/agent/compiler.py`, `openkb/pending.py`)**:
   - Assemble and validate the complete promoted page (all buffered notes + current note + valid frontmatter) in memory BEFORE writing the page file, then commit the page write, `index.md` update, backlinks, and pending-buffer removal cleanly so a mid-promotion `OSError` never strands a partial page on disk alongside an un-cleared buffer.

5. **High-Impact P1 fixes (`openkb/cli.py`, `openkb/pending.py`, `openkb/agent/consolidator.py`, `openkb/agent/compiler.py`, `openkb/lint.py`)**:
   - **`remove` purges `pending_topics.json`**: Removing a document also removes its buffered notes from both `concepts` and `entities` in `pending_topics.json` (pruning empty entries and including it in remove rollback/preview).
   - **Consolidate CLI exit status & index description sync**: Sync updated `description` into `wiki/index.md` on successful consolidation; distinguish `consolidated`, `skipped`, and `failed` counts (preserving existing `[OK]`/`[SKIP]`/`[ERROR]` line formats for downstream callers like `jarvis-workflow-ts`, while returning a non-zero exit code when one or more pages fail so callers never mistake total/partial failure for exit 0; update existing `tests/test_consolidate_cli.py` assertion accordingly).
   - **Promotion backlinks to earlier summaries**: When a pending topic promotes on the 3rd document, add reverse links to the earlier buffered summaries as well as the current document, and sanitize buffered notes against ghost wikilinks on promotion.
   - **`fix_broken_links` bare-stem parity in `explorations/`**: Align `fix_broken_links` with `find_broken_links` so valid bare-stem wikilinks (e.g., `[[alpha]]`) that `find_broken_links` accepts are not stripped by `fix_broken_links`.

6. **End-to-End Integration Tests (`tests/`)**:
   - Add real multi-step CLI + filesystem integration tests (faking only the LLM transport / fault injection point) covering:
     1. Truncated (`length`), metadata-only, non-string description, multiline YAML description, and malformed-YAML `consolidate` runs leaving originals byte-identical and exiting non-zero on failures, plus `summary-rewrite` truncation fallback to v1.
     2. `add a` -> `add b` -> failed `add c` (at `_update_index` after promotion, and after below-threshold `add_note`) proving `pending_topics.json` is restored byte-for-byte (including absent-file restoration) and retry succeeds once.
     3. Mid-promotion write failure (`OSError`) leaving no partial page bypassing `pending_topics.json`.
     4. Full `add a, b` -> `remove a` (purges pending) -> `add c, d` (promotes cleanly without citing deleted `summaries/a.md`, backlinks prior summaries, updates `index.md`) -> `consolidate` -> `lint` (`check_index_sync` + `find_broken_links` + `fix_broken_links` preserving valid `explorations/` bare links).

## Non-Goals

- Do not modify `.no-mistakes.yaml`.
- Keep `openkb/config.py` strictly under 800 lines (`tests/test_file_size.py`).
- Preserve `[OK]`, `[SKIP]`, `[ERROR]`, and `Would consolidate ...` output line prefixes in `openkb consolidate`.

## Verification

```bash
uv run --locked --extra dev --extra api --python 3.12 ruff check .
uv run --locked --extra dev --extra api --python 3.12 ruff format --check .
uv run --locked --extra dev --extra api --python 3.12 mypy openkb
uv run --locked --extra dev --extra api --python 3.12 pytest
git diff --check
```
