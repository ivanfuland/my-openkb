---
spec: "2026-11-23-openkb-pr246-248-268"
version: "v1.0"
project: "my-openkb"
---

# Spec: Merge Upstream OpenKB PR #246 + PR #248 + PR #268 into `my-openkb`

- **Spec ID**: `2026-11-23-openkb-pr246-248-268`
- **Spec Version**: `v1.0`
- **Project**: `my-openkb` (`github.com/ivanfuland/my-openkb`, seeded from `VectifyAI/OpenKB@ff54396e575ee6feb0113b631a34caa082b441cc`)
- **Base Branch**: `main`

## Problem

Nightly `nas-archive` ingestion on `openkb 0.5.0rc2.dev3+gff54396e5` spends 86.2% of total LLM request time (89.2% of output tokens) rewriting entire existing concept/entity pages on every document update, while the planning prompt's concept/entity brief lists have grown to ~180K–210K tokens (~64.4% of entities are one-off pages cited by only a single document).

## Goal

Merge three verbatim upstream pull requests on top of `VectifyAI/OpenKB@ff54396e575ee6feb0113b631a34caa082b441cc` into `ivanfuland/my-openkb`, cleanly resolving only the expected overlap between PR #248 and PR #268 in `openkb/agent/compiler.py` (`_read_*_briefs`), with zero custom hybrid-mode invention:

1. **Upstream PR #246** (`VectifyAI/OpenKB` `refs/pull/246/head`, 5 commits):
   - `51e16cee93` (`concept_update_mode: append`), `9081134dae` (`openkb consolidate`), `a397e61f83` (async full pipeline tests), `5ff4cc48f4` (relaxed note sentence prompt), `27ba79bcef` (`consolidate --all` concurrency).
2. **Upstream PR #248** (`VectifyAI/OpenKB` `refs/pull/248/head`, 5 incremental commits above PR #246's first 3 commits):
   - `53e39768b2` (strict type/word-count gates + pending buffer promoting after 3 docs), `b33ce06e28`, `c1562646ba`, `7bcca160ed` (`strict_item_mode` toggle), `5c7a36123f` (pending buffer description accumulation).
3. **Upstream PR #268** (`VectifyAI/OpenKB` `refs/pull/268/head`, 1 commit `4aa36afb97`):
   - `4aa36afb97` (`briefs_budget_chars`, default 120,000 chars per category, ranking briefs by source count with explicit omission disclosure).

## Non-Goals

- Adding any custom hybrid new-page/update-page mode beyond verbatim PR #246.
- Modifying production `~/.local/share/openkb/nas-archive`, `~/.local/share/openkb/firstmate`, `uv tool` installation, or `jarvis-workflow-ts` (production cutover happens separately after isolated verification).
- Bringing in PR #259 (`TaxonomySearch`) or any unrelated upstream PRs.

## Acceptance Criteria

1. All 11 upstream commits from PR #246 (5), PR #248 (5 incremental), and PR #268 (1) are cleanly integrated onto the task branch based on `ff54396e575ee6feb0113b631a34caa082b441cc`, preserving verbatim upstream behavior for `concept_update_mode: append`, `openkb consolidate`, `strict_item_mode`, pending buffer promotion, and `briefs_budget_chars`.
2. The conflict in `openkb/agent/compiler.py` between PR #248 and PR #268 (`_read_*_briefs`) is resolved so BOTH `strict_item_mode` / pending-buffer filtering AND `briefs_budget_chars` source-count-ranked truncation work together seamlessly.
3. Full test suite (`pytest`) passes with targeted tests covering the combined PR #246 + #248 + #268 interaction (including `strict_item_mode` + `briefs_budget_chars` + `concept_update_mode: append`), and repository lint/type checks (`ruff` / `mypy` as configured in `pyproject.toml`) pass cleanly.
4. Default config preserves backward-compatible behavior when new opt-in toggles are not enabled, and `git diff --check` is clean.
