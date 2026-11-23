"""Regression tests for generation retries and compiler WARN counts."""

from __future__ import annotations

import json
import logging
from collections import Counter
from unittest.mock import AsyncMock

import pytest

from openkb.agent import compiler
from openkb.pending import PendingTopicsStore


async def _compile(kb_dir, mode):
    await compiler._compile_concepts(
        kb_dir / "wiki",
        kb_dir,
        "test-model",
        {"role": "system", "content": "System."},
        {"role": "user", "content": "Document."},
        "Summary.",
        "current-doc",
        max_concurrency=2,
        concept_update_mode=mode,
    )


_ORIGINAL_PAGE = '---\nsources: ["summaries/older-doc.md"]\n---\n\nOriginal content.\n'


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["append", "rewrite"])
async def test_empty_generation_retries_once_and_counts_staged_topics(
    kb_dir, monkeypatch, capsys, caplog, mode
):
    wiki = kb_dir / "wiki"
    (wiki / "entities").mkdir()
    plan = {}
    for group in ("concepts", "entities"):
        for slug in ("recovered", "still-empty"):
            (wiki / group / f"{slug}.md").write_text(_ORIGINAL_PAGE, encoding="utf-8")
        plan[group] = {
            "update": [{"name": "recovered"}, {"name": "still-empty"}],
            "create": [
                {"name": "staged", "type": "organization"}
                if group == "entities"
                else {"name": "staged"}
            ],
        }
    monkeypatch.setattr(compiler, "_llm_call", lambda *args, **kwargs: json.dumps(plan))
    attempts = Counter()

    async def generate(_model, _messages, step, **kwargs):
        attempts[step] += 1
        prefix, slug = step.split(": ")
        empty = slug == "still-empty" or attempts[step] == 1
        # A frontmatter-only rewrite is empty after preprocessing.
        if "-note" in prefix:
            return json.dumps({"note": " \n " if empty else "Recovered content."})
        return json.dumps(
            {"content": _ORIGINAL_PAGE.split("\n\n")[0] if empty else "Recovered content."}
        )

    monkeypatch.setattr(compiler, "_llm_call_page_async", generate)

    with caplog.at_level(logging.WARNING, logger=compiler.__name__):
        await _compile(kb_dir, mode)

    # The retry budget is per prompt, including both kinds of pending notes.
    concept_update = "concept-note-update" if mode == "append" else "update"
    entity_update = "entity-note-update" if mode == "append" else "entity-update"
    assert attempts == {
        **{f"{concept_update}: {slug}": 2 for slug in ("recovered", "still-empty")},
        **{f"{entity_update}: {slug}": 2 for slug in ("recovered", "still-empty")},
        "concept-note: staged": 2,
        "entity-note: staged": 2,
    }
    pending = PendingTopicsStore(kb_dir / ".openkb" / "pending_topics.json")
    for group in ("concepts", "entities"):
        assert "Recovered content." in (wiki / group / "recovered.md").read_text(encoding="utf-8")
        assert (wiki / group / "still-empty.md").read_text(encoding="utf-8") == _ORIGINAL_PAGE
        assert pending.note_count(group, "staged") == 1

    warnings = [line.strip() for line in capsys.readouterr().out.splitlines() if "[WARN]" in line]
    assert warnings == [
        f"[WARN] 3 {kind} planned but only 2 written for current-doc "
        "(1 direct, 1 staged/promoted; ValueError)."
        for kind in ("concept(s)", "entity(ies)")
    ]
    assert [
        record.getMessage() for record in caplog.records if record.name == compiler.__name__
    ] == [
        f"{kind} generation failed: LLM returned empty content for concept 'still-empty'"
        for kind in ("Concept", "Entity")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [compiler.TruncatedResponseError, OSError, ValueError])
async def test_generation_does_not_retry_llm_exceptions(kb_dir, monkeypatch, capsys, error_type):
    monkeypatch.setattr(
        compiler, "_llm_call", lambda *args, **kwargs: '{"create": [{"name": "topic"}]}'
    )
    generate = AsyncMock(side_effect=error_type("Failed in model call"))
    monkeypatch.setattr(compiler, "_llm_call_page_async", generate)

    if error_type is OSError:
        with pytest.raises(OSError, match="Failed in model call"):
            await _compile(kb_dir, "append")
    else:
        await _compile(kb_dir, "append")
        assert (
            f"1 concept(s) planned but only 0 written for current-doc ({error_type.__name__})."
            in capsys.readouterr().out
        )
    generate.assert_awaited_once()
