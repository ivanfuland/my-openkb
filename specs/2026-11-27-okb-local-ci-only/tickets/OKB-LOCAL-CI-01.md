---
ticket: OKB-LOCAL-CI-01
title: "Enable local-CI-only no_ci in my-openkb and switch ci.yml to manual workflow_dispatch"
work_nature: implementation
project: my-openkb
execution_kind: ship
spec: 2026-11-27-okb-local-ci-only
spec_version: "1.0"
deliverables:
  - ".no-mistakes.yaml sets no_ci: true while preserving all existing prepare, lint, format, test commands and preflight-lint gate."
  - ".github/workflows/ci.yml triggers only on workflow_dispatch (removing automatic push and pull_request triggers) while leaving publish.yml untouched."
  - "All existing local lint, format, mypy, and pytest checks pass cleanly."
evidence:
  - "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb"
  - "uv run --locked --extra dev --extra api --python 3.12 pytest"
  - "python3 -c 'import yaml; nm=yaml.safe_load(open(\".no-mistakes.yaml\")); assert nm.get(\"no_ci\") is True; ci=yaml.safe_load(open(\".github/workflows/ci.yml\")); on=ci.get(\"on\", ci.get(True)); assert set(on.keys())=={\"workflow_dispatch\"}'"
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb"
    expect: "exit code 0 with zero lint, format, or type errors"
  - command: "uv run --locked --extra dev --extra api --python 3.12 pytest"
    expect: "exit code 0 with all tests passing"
  - command: "python3 -c 'import yaml; nm=yaml.safe_load(open(\".no-mistakes.yaml\")); assert nm.get(\"no_ci\") is True; ci=yaml.safe_load(open(\".github/workflows/ci.yml\")); on=ci.get(\"on\", ci.get(True)); assert set(on.keys())=={\"workflow_dispatch\"}'"
    expect: "exit code 0 confirming no_ci: true and manual-only workflow_dispatch trigger"
allowed_paths:
  - ".no-mistakes.yaml"
  - ".github/workflows/ci.yml"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: litellm-local-gpt/gpt-6.2-sol
recommended_effort: low
rework_budget: 2
---
# OKB-LOCAL-CI-01: Local-CI-Only Configuration for `my-openkb`

## Task
Implement `specs/2026-11-27-okb-local-ci-only/spec.md` strictly within `allowed_paths`:

1. Edit `.no-mistakes.yaml`:
   - Add `no_ci: true` with a concise comment stating that CI runs locally through `no-mistakes` rather than automatic remote GitHub Actions.
   - Keep `commands.prepare`, `commands.lint`, `commands.format`, `commands.test`, and `gates` (`preflight-lint`) completely intact.
2. Edit `.github/workflows/ci.yml`:
   - Change the `on:` block from `push`/`pull_request` to `workflow_dispatch:` only, with a brief comment explaining that automatic remote CI triggers are disabled in favor of local `no-mistakes` gates.
   - Do not modify `.github/workflows/publish.yml` or any Python/test/doc files.
3. Run the acceptance commands, verify `git status` and `git diff` stay within `allowed_paths`, commit cleanly, and hand off to the Assignment owner.
