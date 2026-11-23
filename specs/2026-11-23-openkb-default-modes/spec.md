---
spec: "2026-11-23-openkb-default-modes"
version: "v1.0"
project: "my-openkb"
---

# Spec: Make `concept_update_mode: append` and `strict_item_mode: true` the Built-in Defaults in `my-openkb`

- **Spec ID**: `2026-11-23-openkb-default-modes`
- **Spec Version**: `v1.0`
- **Project**: `my-openkb` (`github.com/ivanfuland/my-openkb`)
- **Base Branch**: `main`

## Problem

After integrating PR #246 (`concept_update_mode: append`), PR #248 (`strict_item_mode`), and PR #268 (`briefs_budget_chars: 120000`), isolated A/B validation on a 4,941-page KB proved that `append` + `strict_item_mode: true` + `briefs_budget_chars: 120000` cuts single-document compile latency by 82% (5.58x speedup) and prevents one-off page sprawl. However, while `briefs_budget_chars` already defaults to `120000`, `concept_update_mode` still defaults to `"rewrite"` and `strict_item_mode` still defaults to `False`, requiring every KB to opt in manually.

## Goal

Make the validated production-safe settings the built-in code defaults for `my-openkb`:

1. `resolve_concept_update_mode(config)` defaults to `"append"` when `concept_update_mode` is omitted, and degrades invalid values to `"append"` with a warning. Explicit `concept_update_mode: rewrite` continues to work unchanged.
2. `resolve_strict_item_mode(config)` defaults to `True` when `strict_item_mode` is omitted, and degrades non-bool values to `True` with a warning. Explicit `strict_item_mode: false` continues to work unchanged.
3. `briefs_budget_chars` keeps its existing `120_000` default.
4. Update `config.yaml.example`, `README.md`, docstrings, and unit tests to reflect the new defaults while preserving full test coverage for explicit `"rewrite"` and explicit `strict_item_mode: false`.

## Non-Goals

- Removing `"rewrite"` mode or `strict_item_mode: false` support (both must remain explicitly selectable).
- Changing `.no-mistakes.yaml`, touching `~/.local/share/openkb/*`, or reinstalling global `uv tool`.

## Acceptance Criteria

1. `resolve_concept_update_mode({})` returns `"append"`, malformed values warn and return `"append"`, and `resolve_concept_update_mode({"concept_update_mode": "rewrite"})` returns `"rewrite"`.
2. `resolve_strict_item_mode({})` returns `True`, non-bool values warn and return `True`, and `resolve_strict_item_mode({"strict_item_mode": False})` returns `False`.
3. `openkb/config.py` remains strictly under 800 lines, `tests/test_file_size.py` passes unmodified, and `.no-mistakes.yaml` is untouched.
4. Full verification passes: `ruff check .`, `ruff format --check .`, `mypy openkb`, `pytest`, and `git diff --check`.
