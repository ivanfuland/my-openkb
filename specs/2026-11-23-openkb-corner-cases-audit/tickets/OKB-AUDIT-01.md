---
ticket: "OKB-AUDIT-01"
title: "Audit my-openkb append, pending, consolidate, consolidate_model, and integration-test gaps"
work_nature: "drill"
execution_kind: "scout"
spec: "2026-11-23-openkb-corner-cases-audit"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "Produce a prioritized, evidence-backed corner-case and integration-test gap report covering openkb/agent/consolidator.py, openkb/agent/compiler.py, openkb/agent/compiler_notes.py, openkb/pending.py, openkb/compiler_config.py, openkb/config.py, openkb/cli.py, openkb/lint.py, openkb/locks.py, and tests/."
evidence:
  - "Exact file:line citations, concrete trace/reproduction of every bug or corruption hazard (including raise_on_truncation in consolidator.consolidate_page), and an inventory of missing integration tests."
acceptance:
  - command: "git status --short"
    expect: "Worktree is completely clean (read-only scout) and the scout report contains prioritized P0/P1/P2 findings with file:line evidence and actionable fix + integration-test recommendations."
allowed_paths:
  - "specs/"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: "litellm-local-gpt/gpt-6.2-sol"
recommended_effort: "high"
rework_budget: 1
---

# Ticket: OKB-AUDIT-01

## Context

`my-openkb` recently landed several major changes (`concept_update_mode: append` + `strict_item_mode: true` defaults, `briefs_budget_chars`, `pending_topics`, `openkb consolidate`, and `consolidate_model`). Telemetry observation already flagged one silent data-loss hazard (`consolidate_page` calling `_llm_call_async` without `raise_on_truncation=True`).

## Required Audit

Read the real source and tests (do not modify tracked files) and audit:

1. **Truncation & silent overwrite hazards**:
   - Inspect `openkb/agent/consolidator.py` and every `_llm_call_async` call in `openkb/agent/`. Which ones pass `raise_on_truncation=True` and which do not? What happens on truncated output, missing keys, or malformed frontmatter?
2. **`consolidate` & `consolidate_model` edge cases**:
   - Check `openkb/cli.py:consolidate()`, `_setup_llm_key(model_override=...)`, `resolve_consolidate_model()`, `openkb/config.py` (including 800-line ceiling), cross-provider env propagation, `OPENAI_API_BASE` / `extra_headers` / `timeout`, and error exit codes when all/some pages fail.
3. **`append` + `pending_topics` + `lint` + `locks` interactions**:
   - Check promotion from `pending_topics.json` to `wiki/concepts/` and `wiki/entities/`, `index.md` sync, backlinks, `remove` cleanup, `explorations/` broken-link checks, duplicate `## Notes` headings, and lock behavior across concurrent `add` + `consolidate`.
4. **Integration-test coverage gaps** (`tests/`):
   - Audit existing tests (`tests/test_consolidator.py`, `tests/test_consolidate_cli.py`, `tests/test_pending.py`, `tests/test_config.py`, `tests/test_lint.py`, etc.) and list concrete end-to-end integration tests needed to cover multi-step workflows rather than isolated mocks.

## Output Format

Organize into **P0 (Data loss / silent corruption)**, **P1 (Functional bugs / contract mismatches)**, **P2 (Edge cases / hardening)**, and **Integration Test Plan** with exact `file:line` citations.
