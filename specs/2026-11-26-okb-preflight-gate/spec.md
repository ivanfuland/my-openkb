---
spec: 2026-11-26-okb-preflight-gate
version: "1.0"
---
# Spec: Wire Shared `myhome-preflight-lint` Gate in `my-openkb`

## Goal
Add the shared cross-platform deterministic preflight lint gate (`myhome-preflight-lint`, running `prek`, `gitleaks`, UTF-8/syntax checks, and `ast-grep`) to `my-openkb`'s `.no-mistakes.yaml` anchored at `after: rebase`, so mechanical hygiene, secret, and rule issues are caught before the LLM review step.

## Required Configuration
Add this exact `gates:` entry to `.no-mistakes.yaml` without altering any existing configuration keys:

```yaml
gates:
  - name: preflight-lint
    after: rebase
    command: "${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint"
```

## Non-Goals
- Do not change any existing keys, commands, instructions, or comments in `.no-mistakes.yaml`.
- Do not modify any files outside `.no-mistakes.yaml`.
