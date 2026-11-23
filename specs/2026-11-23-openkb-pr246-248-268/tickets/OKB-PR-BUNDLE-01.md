---
ticket: "OKB-PR-BUNDLE-01"
title: "Merge verbatim upstream OpenKB PR #246, PR #248, and PR #268 and resolve compiler.py brief-list conflict"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-pr246-248-268"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "Integrate all 11 upstream commits from VectifyAI/OpenKB PR #246 (5 commits), PR #248 (5 incremental commits), and PR #268 (1 commit 4aa36afb97) cleanly on top of ff54396e575ee6feb0113b631a34caa082b441cc without inventing custom hybrid modes."
  - "Resolve the expected overlap between PR #248 and PR #268 in openkb/agent/compiler.py (_read_*_briefs) so strict_item_mode and briefs_budget_chars compose cleanly."
  - "Add/verify combined unit tests covering PR #246 (append + consolidate) + PR #248 (strict_item_mode + pending buffer) + PR #268 (briefs_budget_chars) working together, and ensure full pytest and configured lint/type checks pass."
evidence:
  - "Full pytest run (including new combined interaction tests), ruff/mypy checks if configured in pyproject.toml, and git diff --check."
acceptance:
  - command: "uv run pytest && git diff --check"
    expect: "All existing upstream tests, all tests brought in by PR #246/#248/#268, and combined PR #248+#268 interaction tests pass with zero failures; git diff --check is clean."
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

# Ticket: OKB-PR-BUNDLE-01

## Context

`my-openkb` is seeded from `VectifyAI/OpenKB@ff54396e575ee6feb0113b631a34caa082b441cc` (`main`). The upstream repository has three verified open/closed PRs that together address full-page rewrite latency (86.2% of nightly compile time) and planning brief-list bloat (~200K tokens):

1. **PR #246** (`https://github.com/VectifyAI/OpenKB.git` `refs/pull/246/head`, tip `27ba79bcef3c28935ca218c1809501ad8738fb02`, 5 commits above `ff54396e5`):
   - `51e16cee93` (`concept_update_mode: append`)
   - `9081134dae` (`openkb consolidate`)
   - `a397e61f83` (async full pipeline tests)
   - `5ff4cc48f4` (relaxed note sentence prompt)
   - `27ba79bcef` (`consolidate --all` concurrency)
2. **PR #248** (`https://github.com/VectifyAI/OpenKB.git` `refs/pull/248/head`, tip `5c7a36123fcdb32229df83514a077fd7091a9ef7`, stacks on PR #246's first 3 commits; take its 5 incremental commits):
   - `53e39768b2`, `b33ce06e28`, `c1562646ba`, `7bcca160ed`, `5c7a36123f` (`strict_item_mode` + pending buffer with description accumulation)
3. **PR #268** (`https://github.com/VectifyAI/OpenKB.git` `refs/pull/268/head`, tip `4aa36afb97da75232ec615fd0164739e8c22532c`, 1 commit above `ff54396e5`):
   - `4aa36afb97` (`briefs_budget_chars`, default 120,000 chars per category, ranked by source count with explicit omission disclosure)

## Required changes

1. Fetch the three upstream PR refs from `https://github.com/VectifyAI/OpenKB.git` (`refs/pull/246/head`, `refs/pull/248/head`, `refs/pull/268/head`) and verify their exact commit hashes against the list above.
2. Cherry-pick / integrate in order on top of the task branch:
   - First, all 5 commits of PR #246 (`ff54396e5..27ba79bcef`);
   - Second, the 5 incremental commits of PR #248 (those not already in PR #246: `53e39768b2`, `b33ce06e28`, `c1562646ba`, `7bcca160ed`, `5c7a36123f`);
   - Third, the 1 commit of PR #268 (`4aa36afb97`).
   Do NOT invent any custom hybrid new-page/update-page mode beyond verbatim PR #246.
3. Resolve the overlap between PR #248 and PR #268 in `openkb/agent/compiler.py` (around `_read_*_briefs` and any adjacent config/prompt code) cleanly so that both `strict_item_mode` / pending-buffer behavior and `briefs_budget_chars` source-count-ranked truncation work together without dropping either feature's logic or tests.
4. Add focused unit tests in `tests/` verifying the combined behavior of PR #246 (`concept_update_mode: append` + `consolidate`), PR #248 (`strict_item_mode` + pending buffer), and PR #268 (`briefs_budget_chars`) enabled simultaneously.
5. Run the full test suite (`uv run pytest`, or the repo's venv/pytest command if `uv` needs `--offline`/`--frozen` — inspect `pyproject.toml` first), run any configured linter/type-checker (`ruff`, `mypy`), verify `git diff --check` is clean, and do NOT touch any real KB under `~/.local/share/openkb/` or reinstall global `uv tool`.
