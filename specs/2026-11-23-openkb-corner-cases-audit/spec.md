---
spec: "2026-11-23-openkb-corner-cases-audit"
version: "v1.0"
project: "my-openkb"
---

# Spec: End-to-End Corner-Case and Integration-Test Audit for `my-openkb`

- Spec ID: `2026-11-23-openkb-corner-cases-audit`
- Spec Version: `v1.0`
- Project: `my-openkb`
- Base Branch: `main`

## Goal

Perform a thorough, read-only corner-case and integration-test audit of `my-openkb` focusing on the recently integrated compilation, pending-topics, consolidation, `consolidate_model`, linting, and locking paths so silent corruption, truncation, provider mismatch, and untested integration flows are surfaced proactively.

## Audit Scope

1. **Silent truncation & overwrite risks** (`openkb/agent/consolidator.py`, `openkb/agent/compiler.py`, `openkb/agent/compiler_notes.py`):
   - Verify `consolidator.consolidate_page` missing `raise_on_truncation=True` (and check every other `_llm_call_async` / LLM call site across `openkb/agent/`).
   - Check what happens when LLM returns empty/truncated JSON, strips frontmatter, drops `sources`, or alters headings.
2. **`consolidate_model` & credential/provider setup** (`openkb/compiler_config.py`, `openkb/config.py`, `openkb/cli.py`):
   - Check cross-provider `model` vs `consolidate_model`, OAuth providers, `resolve_credential_bundle`, `litellm:` settings, `extra_headers`, `timeout`, and REST API endpoints (`/api/v1/config`, `/api/v1/recompile`).
3. **`append` + `pending_topics` + `consolidate` + `lint` interactions**:
   - Check re-ingest idempotency, concurrent lock contention (`kb_lock`), `explorations/` broken-link handling, ghost-wikilink stripping, `index.md` sync, and CLI output compatibility for downstream callers (`--dry-run`, `[OK]`, `[SKIP]`, `[ERROR]`, exit codes).
4. **Integration-test gaps** (`tests/`):
   - Identify missing end-to-end integration tests across `add` -> `pending` -> promote -> `append` -> `consolidate` (with `consolidate_model`) -> `lint` -> `remove`.

## Deliverable

Write a prioritized, evidence-backed report with exact `file:line` citations, reproduction steps, and concrete fix + integration-test recommendations. Do not modify any repository files.
