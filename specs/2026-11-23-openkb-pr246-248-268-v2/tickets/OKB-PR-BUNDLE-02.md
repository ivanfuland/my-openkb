---
ticket: "OKB-PR-BUNDLE-02"
title: "Merge verbatim upstream OpenKB PR #246, PR #248, and PR #268 onto main with .no-mistakes.yaml"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-pr246-248-268-v2"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "Integrate all 11 upstream commits from VectifyAI/OpenKB PR #246 (5 commits), PR #248 (5 incremental commits), and PR #268 (1 commit 4aa36afb97) cleanly on top of main without inventing custom hybrid modes."
  - "Resolve the expected overlap between PR #248 and PR #268 in openkb/agent/compiler.py (_read_*_briefs) so strict_item_mode and briefs_budget_chars compose cleanly."
  - "Include combined unit tests covering PR #246 (append + consolidate) + PR #248 (strict_item_mode + pending buffer) + PR #268 (briefs_budget_chars) working together, and ensure full pytest, ruff, mypy, and git diff --check pass."
evidence:
  - "Full pytest run (including combined interaction tests), ruff check, ruff format --check, mypy openkb, and git diff --check."
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb && uv run --locked --extra dev --extra api --python 3.12 pytest && git diff --check"
    expect: "All existing upstream tests, all tests brought in by PR #246/#248/#268, and combined interaction tests pass with zero failures; ruff, mypy, and git diff --check are clean; .no-mistakes.yaml is untouched."
allowed_paths:
  - "openkb/"
  - "tests/"
  - "README.md"
  - "docs/"
  - "pyproject.toml"
  - "specs/"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: "litellm-local-gpt/gpt-6.2-sol"
recommended_effort: "high"
rework_budget: 2
---

# Ticket: OKB-PR-BUNDLE-02

## Context

`my-openkb` `main` is seeded from `VectifyAI/OpenKB@ff54396e575ee6feb0113b631a34caa082b441cc` plus a repository-root `.no-mistakes.yaml` aligned with `.github/workflows/ci.yml`.
An earlier integration attempt already integrated all 11 upstream commits from PR #246 (5 commits), PR #248 (5 incremental commits), and PR #268 (1 commit `4aa36afb97`), resolved the `openkb/agent/compiler.py` `_read_*_briefs` overlap, and added combined interaction + fixture adaptation tests (13 verified commits total), exported as patch series at:
`/home/ivan/.local/share/fm/data/openkb-patches-85d49d1/` (`0001-*.patch` through `0013-*.patch`).

## Required changes

1. Apply the verified 13-commit patch series from `/home/ivan/.local/share/fm/data/openkb-patches-85d49d1/*.patch` in order (`git am /home/ivan/.local/share/fm/data/openkb-patches-85d49d1/*.patch`) on top of the current task branch.
2. Verify that:
   - All 11 upstream commits from PR #246, PR #248, and PR #268 plus the 2 test commits applied cleanly;
   - `.no-mistakes.yaml` is completely untouched (`git diff origin/main -- .no-mistakes.yaml` is empty);
   - No custom hybrid mode beyond verbatim PR #246 was introduced;
   - No files outside `allowed_paths` were modified.
3. Run the full verification suite cleanly:
   - `uv sync --locked --extra dev --extra api --python 3.12`
   - `uv run --no-sync ruff check .`
   - `uv run --no-sync ruff format --check .`
   - `uv run --no-sync mypy openkb`
   - `uv run --no-sync pytest`
   - `git diff --check`
4. Do NOT touch any real KB under `~/.local/share/openkb/` or reinstall global `uv tool`.
