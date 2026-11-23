---
ticket: "OKB-CONS-MODEL-01"
title: "Add optional consolidate_model config setting for openkb consolidate"
work_nature: "implementation"
execution_kind: "ship"
spec: "2026-11-23-openkb-consolidate-model"
spec_version: "v1.0"
project: "my-openkb"
deliverables:
  - "openkb/compiler_config.py & openkb/config.py: add resolve_consolidate_model(config: dict) -> str in openkb/compiler_config.py and re-export it from openkb/config.py while keeping openkb/config.py strictly under 800 lines."
  - "openkb/cli.py: update _setup_llm_key to accept optional keyword-only model_override: str | None = None for provider detection, and wire consolidate() to resolve model via resolve_consolidate_model(config) and pass model_override=model to _setup_llm_key without changing existing CLI output lines."
  - "config.yaml.example & README.md: document optional consolidate_model under Compilation settings."
  - "tests/test_config.py & tests/test_consolidate_cli.py: add unit and CLI tests covering resolve_consolidate_model (unset, None, valid override, whitespace trimming, invalid types/blank warning+fallback), consolidate model override/fallback, and provider detection with model_override."
evidence:
  - "uv run --locked --extra dev --extra api --python 3.12 ruff check ., ruff format --check ., mypy openkb, pytest (including tests/test_file_size.py, tests/test_config.py, tests/test_consolidate_cli.py), and git diff --check."
acceptance:
  - command: "uv run --locked --extra dev --extra api --python 3.12 ruff check . && uv run --locked --extra dev --extra api --python 3.12 ruff format --check . && uv run --locked --extra dev --extra api --python 3.12 mypy openkb && uv run --locked --extra dev --extra api --python 3.12 pytest && git diff --check"
    expect: "All lint, format, mypy, pytest checks (including file size limit) and git diff --check pass; .no-mistakes.yaml is untouched."
allowed_paths:
  - "openkb/compiler_config.py"
  - "openkb/config.py"
  - "openkb/cli.py"
  - "config.yaml.example"
  - "README.md"
  - "tests/test_config.py"
  - "tests/test_consolidate_cli.py"
  - "specs/"
blocked_by: []
discovered_from: ""
supersedes: []
recommended_model: "litellm-local-gpt/deepseek-flash-oq4e"
recommended_effort: "off"
rework_budget: 2
---

# Ticket: OKB-CONS-MODEL-01

## Summary

Add optional `consolidate_model` setting to KB `.openkb/config.yaml` so `openkb consolidate` can run with a different model than `model` (falling back to `model` when unset or invalid).

## Requirements

1. **`openkb/compiler_config.py` & `openkb/config.py`**:
   - Define `DEFAULT_MODEL = "gpt-5.4"` (matching `DEFAULT_CONFIG["model"]`) and `resolve_consolidate_model(config: dict) -> str` in `openkb/compiler_config.py`.
   - Re-export `resolve_consolidate_model` from `openkb/config.py`. Keep `openkb/config.py` strictly under 800 lines (`tests/test_file_size.py` enforces this).
   - Behavior of `resolve_consolidate_model(config)`:
     - Resolve `fallback`: if `config.get("model")` is a non-empty `str` (stripped), use `config["model"].strip()`; otherwise fall back to `DEFAULT_MODEL`.
     - If `"consolidate_model"` is not in `config` or `config["consolidate_model"] is None`: return `fallback` silently (no warning).
     - If `isinstance(value, str)` and `value.strip()`: return `value.strip()`.
     - Otherwise (non-string such as `bool`, `int`, `list`, `dict`, or empty/whitespace-only string): log a warning on logger `"openkb.config"` and return `fallback`.
   - Keep `consolidate_model` out of `GLOBAL_SCALAR_KEYS` and `DEFAULT_CONFIG`.

2. **`openkb/cli.py`**:
   - Import `resolve_consolidate_model` from `openkb.config`.
   - Extend `_setup_llm_key(kb_dir: Path | None = None, *, model_override: str | None = None) -> None` so provider auto-detection uses `model_override` when provided (and falls back to `config.get("model", DEFAULT_CONFIG["model"])` when `model_override` is `None`).
   - In `consolidate()`:
     - Resolve `config = resolve_effective_config(kb_dir)[0]` and `model: str = resolve_consolidate_model(config)`.
     - Call `_setup_llm_key(kb_dir, model_override=model)`.
     - Pass `model` to `consolidator.consolidate_pages(wiki_dir, targets, model, language, max_concurrency)`.
     - Do not change existing `click.echo(...)` stdout lines or `--dry-run` behavior.

3. **Documentation**:
   - Update `config.yaml.example` under the compilation settings comments to show `# consolidate_model: ...`.
   - Update `README.md` under `### Compilation settings` with a concise `consolidate_model` row and mention its warning/fallback behavior on invalid values.

4. **Tests**:
   - Add unit tests in `tests/test_config.py` covering `resolve_consolidate_model`: unset, explicit `None`, valid override, whitespace trimming, empty/whitespace string warning + fallback, and non-string (`int`, `bool`, `list`) warning + fallback.
   - Add tests in `tests/test_consolidate_cli.py` verifying:
     - `consolidate` passes `consolidate_model` to `consolidator.consolidate_page` when configured in `.openkb/config.yaml`.
     - `consolidate` falls back to `model` when `consolidate_model` is absent or `null`.
     - Provider key setup in `_setup_llm_key` respects `consolidate_model` (e.g., when `model` and `consolidate_model` use different providers, or OAuth provider override skips missing-key warning).

## Out of Scope

- Do not touch `.no-mistakes.yaml`.
- Do not change REST API config endpoints or `GLOBAL_SCALAR_KEYS`.
- Do not change `openkb add`, `openkb recompile`, `openkb query`, or `openkb chat` model resolution.
