---
spec: 2026-11-27-okb-local-ci-only
version: "1.0"
---
# Spec: Switch `my-openkb` to Local-CI-Only (`no_ci: true`) and Disable Automatic Remote CI Triggers

## Goal
Align `my-openkb` with the fleet-wide local-CI-only policy so private GitHub Actions runs are no longer triggered automatically on pushes or pull requests, while keeping all existing deterministic local checks (`prepare`, `lint`, `format`, `test`, and `preflight-lint`) enforced by `no-mistakes`.

## Required Changes
1. **`.no-mistakes.yaml`**:
   - Add `no_ci: true` with a concise comment noting that this private repository runs all CI checks locally via `no-mistakes` instead of remote GitHub Actions.
   - Update the top comment if it implies `.github/workflows/ci.yml` runs automatically on every PR.
   - Preserve all existing `commands` (`prepare`, `lint`, `format`, `test`) and `gates` (`preflight-lint`) verbatim.
2. **`.github/workflows/ci.yml`**:
   - Replace the automatic `push` and `pull_request` triggers under `on:` with manual `workflow_dispatch:` only, so pushing branches or opening pull requests never starts billed remote GitHub Actions jobs while preserving the workflow definition for optional manual invocation.
   - Leave `.github/workflows/publish.yml` untouched (it only fires on explicit `v*` release tags).

## Non-Goals
- Do not modify Python source code, tests, dependencies, `AGENTS.md`, or `.github/workflows/publish.yml`.

## Verification
- `uv run --locked --extra dev --extra api --python 3.12 ruff check .`
- `uv run --locked --extra dev --extra api --python 3.12 ruff format --check .`
- `uv run --locked --extra dev --extra api --python 3.12 mypy openkb`
- `uv run --locked --extra dev --extra api --python 3.12 pytest`
- Verify `.no-mistakes.yaml` parses as valid YAML with `no_ci: true` and `.github/workflows/ci.yml` triggers only on `workflow_dispatch`.
