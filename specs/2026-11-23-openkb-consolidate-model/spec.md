---
spec: "2026-11-23-openkb-consolidate-model"
version: "v1.0"
project: "my-openkb"
---

# Spec: Optional `consolidate_model` Setting for `openkb consolidate`

- Spec ID: `2026-11-23-openkb-consolidate-model`
- Spec Version: `v1.0`
- Project: `my-openkb`
- Base Branch: `main`

## Goal

Allow each OpenKB knowledge base to optionally specify `consolidate_model` in `.openkb/config.yaml` so everyday `openkb add` (fast `append` mode) and periodic `openkb consolidate` (full-page prose synthesis) can use different models.

See the [compilation settings reference](../../README.md#compilation-settings) for the user-facing configuration behavior.

## Scope

1. **Config resolver (`openkb/compiler_config.py` & `openkb/config.py`)**:
   - Add `resolve_consolidate_model(config: dict) -> str` in `openkb/compiler_config.py` and re-export it from `openkb/config.py` (keeping `openkb/config.py` strictly under 800 lines per `tests/test_file_size.py`).
   - Resolution rules:
     - Determine `fallback`: `config.get("model")` if it is a non-empty string (stripped), else `"gpt-5.4"` (`DEFAULT_MODEL` matching `DEFAULT_CONFIG["model"]`).
     - If `"consolidate_model"` is absent from `config` or its value is `None`: return `fallback` silently (no warning).
     - If `"consolidate_model"` is a `str` with `value.strip()` non-empty: return `value.strip()`.
     - Otherwise (non-string such as `bool`, `int`, `list`, `dict`, or empty/whitespace-only string): log a warning via `openkb.config` logger and return `fallback`.
   - Do **not** add `consolidate_model` to `GLOBAL_SCALAR_KEYS` or `DEFAULT_CONFIG` (it is an optional KB `.openkb/config.yaml` setting, matching `concurrency` and `timeout`, and avoiding unexpected API/global schema changes).

2. **CLI wiring (`openkb/cli.py`)**:
   - In `consolidate()`:
     - Resolve `config = resolve_effective_config(kb_dir)[0]` and `model = resolve_consolidate_model(config)`.
     - Update `_setup_llm_key(kb_dir: Path | None = None, *, model_override: str | None = None) -> None` so that when `model_override` is passed, provider extraction uses `model_override` instead of `config.get("model", ...)`, while keeping default `model_override=None` 100% backward compatible for all other callers.
     - Call `_setup_llm_key(kb_dir, model_override=model)` in `consolidate()` before running `consolidator.consolidate_pages(wiki_dir, targets, model, language, max_concurrency)`.
     - Preserve all existing `click.echo(...)` output lines and formatting in `consolidate()` so downstream parsers remain compatible.

3. **Docs (`config.yaml.example`, `README.md`)**:
   - Document commented-out `# consolidate_model: ...` in `config.yaml.example` under Compilation settings.
   - Add a `consolidate_model` row to the `Compilation settings` table in `README.md` (and note invalid-value warning/fallback alongside `concept_update_mode` and `strict_item_mode`).

4. **Tests (`tests/test_config.py`, `tests/test_consolidate_cli.py`)**:
   - Unit tests for `resolve_consolidate_model`: absent key, explicit `None`, valid override (including surrounding whitespace trimmed), invalid types (`bool`, `int`, `list`), empty/whitespace-only string (warns and falls back to `model`).
   - CLI tests for `openkb consolidate`:
     - When `consolidate_model` is set in `.openkb/config.yaml`, `consolidator.consolidate_page` receives `consolidate_model` (not `model`), and `_setup_llm_key` resolves provider from `consolidate_model`.
     - When `consolidate_model` is absent or `null`, `consolidator.consolidate_page` receives `model`.

## Non-Goals

- Do not modify `.no-mistakes.yaml`.
- Do not change `openkb add`, `openkb recompile`, `openkb query`, `openkb chat`, or REST API config schema.
- Do not exceed 800 lines in `openkb/config.py`.

## Verification

```bash
uv run --locked --extra dev --extra api --python 3.12 ruff check .
uv run --locked --extra dev --extra api --python 3.12 ruff format --check .
uv run --locked --extra dev --extra api --python 3.12 mypy openkb
uv run --locked --extra dev --extra api --python 3.12 pytest
git diff --check
```
