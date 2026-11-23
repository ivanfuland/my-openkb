---
ticket: "OKB-DEFAULT-01"
title: "Flip built-in defaults to concept_update_mode=append and strict_item_mode=true"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-default-modes"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "Update openkb/compiler_config.py so resolve_concept_update_mode defaults to 'append' (and invalid values fall back to 'append') and resolve_strict_item_mode defaults to True (and invalid values fall back to True)."
  - "Update any inline default references in openkb/ (e.g., config.py, compiler.py, cli.py), config.yaml.example, and README.md so documentation and runtime defaults match."
  - "Update existing tests that implicitly relied on the old 'rewrite' / False defaults by either asserting the new defaults (for default-behavior tests) or passing explicit concept_update_mode='rewrite' / strict_item_mode=False (for rewrite/non-strict feature tests), preserving full coverage of both modes."
evidence:
  - "Full ruff check, ruff format --check, mypy openkb, pytest, and git diff --check."
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb && uv run --locked --extra dev --extra api --python 3.12 pytest && git diff --check"
    expect: "All checks and tests pass with zero failures; default config resolves to append + strict_item_mode=True; explicit rewrite and strict_item_mode=False still pass; .no-mistakes.yaml is untouched."
allowed_paths:
  - "openkb/"
  - "tests/"
  - "README.md"
  - "docs/"
  - "config.yaml.example"
  - "specs/"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: "litellm-local-gpt/gpt-6.2-sol"
recommended_effort: "high"
rework_budget: 2
---

# Ticket: OKB-DEFAULT-01

## Context

`my-openkb` currently inherits upstream PR #246 and PR #248 defaults (`concept_update_mode: "rewrite"` and `strict_item_mode: False`), whereas `briefs_budget_chars` already defaults to `120_000`. Real-scale isolated validation showed that `append` + `strict_item_mode: True` + `briefs_budget_chars: 120000` delivers a 5.58x speedup and eliminates single-use page sprawl, so these should be the built-in defaults of `my-openkb`.

## Required changes

1. In `openkb/compiler_config.py`:
   - Change `resolve_concept_update_mode(config)` default and invalid-value fallback from `"rewrite"` to `"append"` (update docstring and warning message accordingly).
   - Change `resolve_strict_item_mode(config)` default and non-bool fallback from `False` to `True` (update docstring and warning message accordingly).
2. Audit `openkb/` (including `openkb/config.py`, `openkb/agent/compiler.py`, `openkb/cli.py`, and REST/config schema endpoints if any) for any hardcoded default `"rewrite"` or `strict_item_mode=False` defaults or `DEFAULT_CONFIG` entries so everything is consistent with the new defaults.
3. Update `config.yaml.example` (if present) and `README.md` (`Compilation settings`) to document `"append"` and `true` as the defaults and `"rewrite"` / `false` as opt-out options.
4. Update affected tests in `tests/`:
   - Update config resolver tests (`tests/test_config.py`) to assert `"append"` and `True` as defaults and fallback values, while still explicitly testing `"rewrite"` and `False`.
   - For existing compiler/API tests that were specifically testing full-page rewrite behavior or non-strict mode without setting config keys, pass explicit `concept_update_mode: rewrite` and/or `strict_item_mode: false` rather than weakening assertions.
   - Verify `tests/test_file_size.py` passes cleanly (`openkb/config.py` stays strictly under 800 lines).
5. Run full `uv sync --locked --extra dev --extra api --python 3.12`, `ruff check .`, `ruff format --check .`, `mypy openkb`, `pytest`, and `git diff --check`. Do NOT touch `.no-mistakes.yaml`, real KBs under `~/.local/share/openkb/`, or global `uv tool`.
