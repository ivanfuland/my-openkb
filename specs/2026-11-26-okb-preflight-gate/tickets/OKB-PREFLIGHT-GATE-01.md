---
ticket: OKB-PREFLIGHT-GATE-01
title: "Wire shared myhome-preflight-lint after:rebase gate in .no-mistakes.yaml"
work_nature: implementation
project: my-openkb
execution_kind: ship
spec: 2026-11-26-okb-preflight-gate
spec_version: "1.0"
deliverables:
  - "Added the cross-platform preflight-lint custom gate (after: rebase) to .no-mistakes.yaml while keeping all existing configuration untouched."
evidence:
  - "python3 -c \"import yaml; c=yaml.safe_load(open('.no-mistakes.yaml')); g=[x for x in c.get('gates',[]) if x.get('name')=='preflight-lint']; assert len(g)==1 and g[0].get('after')=='rebase' and g[0].get('command')=='${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint', g\""
  - "${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint -- .no-mistakes.yaml"
acceptance:
  - command: "python3 -c \"import yaml; c=yaml.safe_load(open('.no-mistakes.yaml')); g=[x for x in c.get('gates',[]) if x.get('name')=='preflight-lint']; assert len(g)==1 and g[0].get('after')=='rebase' and g[0].get('command')=='${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint', g\""
    expect: "exit code 0 with exactly one preflight-lint gate anchored at after: rebase using the cross-platform MY_HOME fallback command"
  - command: "${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint -- .no-mistakes.yaml"
    expect: "exit code 0 on the updated .no-mistakes.yaml"
allowed_paths:
  - ".no-mistakes.yaml"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: litellm-local-gpt/gpt-6.2-sol
recommended_effort: low
rework_budget: 2
---
# OKB-PREFLIGHT-GATE-01: Wire `myhome-preflight-lint` Gate in `.no-mistakes.yaml`

## Task
Append the following `gates:` block to `.no-mistakes.yaml` (preserving every existing key, value, and comment verbatim):

```yaml
gates:
  - name: preflight-lint
    after: rebase
    command: "${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint"
```

Verify that:
1. `.no-mistakes.yaml` parses as valid YAML and contains the exact `preflight-lint` gate with `after: rebase` and `command: "${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint"`.
2. Running `${MY_HOME:-$HOME/my-home}/bin/myhome-preflight-lint -- .no-mistakes.yaml` exits 0.
3. No other files are modified and the worktree is clean after committing.
