"""Real CLI, compiler and filesystem regression tests for destructive mutations."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from openkb import frontmatter
from openkb.agent import compiler, consolidator
from openkb.cli import cli
from openkb.indexer import CloudImportData
from openkb.lint import find_broken_links
from openkb.pending import PendingTopicsStore, pending_topics_path


def _reply(content, finish="stop"):
    if not isinstance(content, str):
        content = json.dumps(content)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=20),
    )


def _message_text(message):
    value = message["content"]
    if isinstance(value, str):
        return value
    return "".join(block.get("text", "") for block in value)


class ScriptedModel:
    def __init__(self):
        self.summary_rewrite = None
        self.consolidations = {}
        self.consolidation_calls = []
        self.fail_concept_rewrite = False
        self.notes = {}

    def complete(self, *, messages, **_):
        first_doc = _message_text(messages[1])
        prompt = _message_text(messages[-1])
        if prompt.startswith("New document:"):
            doc = first_doc.splitlines()[0].removeprefix("New document: ")
            return _reply(
                {"content": f"Intact v1 facts for {doc}.", "description": "Summary brief"}
            )
        if prompt.startswith("This is a PageIndex summary"):
            return _reply("Cloud overview")
        if prompt.startswith("Based on the summary above"):
            return _reply(
                {
                    "concepts": {"create": [{"name": "alpha"}]},
                    "entities": {"create": [{"name": "alpha", "type": "organization"}]},
                }
            )
        if prompt.startswith("Task: Rewrite the summary"):
            return self.summary_rewrite or _reply("Full summary rewrite.")
        raise AssertionError(prompt)

    async def acomplete(self, *, messages, **_):
        prompt = _message_text(messages[-1])
        if prompt.startswith("Consolidate the "):
            kind = prompt.split()[2]
            self.consolidation_calls.append(kind)
            return self.consolidations[kind]
        if prompt.startswith("Write the "):
            if self.fail_concept_rewrite and prompt.startswith("Write the concept"):
                raise RuntimeError("scripted concept generation failure")
            return _reply(
                {
                    "description": "Rewrite brief",
                    "content": "Curated topic facts. [[concepts/alpha]]",
                }
            )
        if "summarized above" in prompt and (match := re.search(r'document "([^"]+)"', prompt)):
            doc = match[1]
            note = self.notes.get(doc, f"Note from {doc}. [[ghost]]")
            return _reply({"description": f"Brief from {doc}", "note": note})
        raise AssertionError(prompt)


def _invoke(kb, *args):
    return CliRunner().invoke(cli, ["--kb-dir", str(kb), *args])


def _add(kb, name, *, fails=False):
    path = _input(kb, name)
    result = _invoke(kb, "add", str(path))
    marker = f"[ERROR] add failed for {name}.md:" if fails else f"[OK] {name}.md added"
    assert marker in result.output, result.output
    return result


def _input(kb, name):
    path = kb / "incoming" / f"{name}.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"# Document {name}\n\nDistinct facts recorded by {name}.\n", encoding="utf-8")
    return path


def _topic(kb, kind):
    return kb / "wiki" / kind / "alpha.md"


def _state(kb):
    """Read committed artifacts byte for byte, excluding lock and journal internals."""
    paths = [*kb.glob("wiki/**/*"), *kb.glob("raw/**/*"), *kb.glob(".openkb/*.json")]
    return {path.relative_to(kb): path.read_bytes() for path in paths if path.is_file()}


@pytest.fixture
def scripted(kb_dir, monkeypatch):
    import openkb.config as config

    monkeypatch.setattr(config, "GLOBAL_CONFIG_DIR", kb_dir / "isolated-global")
    monkeypatch.setenv("OPENAI_API_KEY", "scripted-test-key")
    (kb_dir / ".openkb" / "config.yaml").write_text("model: gpt-4o-mini\n", encoding="utf-8")
    model = ScriptedModel()
    monkeypatch.setattr(compiler.litellm, "completion", model.complete)
    monkeypatch.setattr(compiler.litellm, "acompletion", model.acomplete)
    return model


@pytest.mark.parametrize(
    ("response", "finish"),
    [
        ('{"description":"New","content":"Partial prose', "length"),
        ({"description": "New", "content": "Complete JSON with partial prose"}, "length"),
        ({"description": "New", "body": "Wrong key"}, "stop"),
        ({"content": ["Bad body type"]}, "stop"),
        ({"content": "---\nfoo: bar\n---"}, "stop"),
        ("false", "stop"),
        ('```json\n"not a page"\n```', "stop"),
    ],
)
def test_consolidate_rejects_unsafe_rewrite(kb_dir, scripted, response, finish):
    for doc in ("a", "b", "c", "d"):
        _add(kb_dir, doc)
    page = _topic(kb_dir, "concepts")
    fm, body = frontmatter.split(page.read_text())
    page.write_text(fm + "\nManual prose that must survive.\n\n" + body)
    before = page.read_bytes()
    index_before = (kb_dir / "wiki" / "index.md").read_bytes()
    scripted.consolidations["concept"] = _reply(response, finish)
    result = _invoke(kb_dir, "consolidate", "alpha")
    assert result.exit_code == 1, result.output
    assert "[ERROR] Consolidation failed:" in result.output
    assert "[OK]" not in result.output
    assert "consolidated 0, skipped 0, failed 1" in result.output
    assert page.read_bytes() == before
    assert (kb_dir / "wiki" / "index.md").read_bytes() == index_before
    assert "consolidated 0, skipped 0, failed 1" in (kb_dir / "wiki" / "log.md").read_text()


def test_malformed_input_is_rejected_before_model_and_other_page_succeeds(kb_dir, scripted):
    for doc in ("a", "b", "c"):
        _add(kb_dir, doc)
    concept = _topic(kb_dir, "concepts")
    original = concept.read_bytes()
    malformed = original.replace(b'type: "Concept"', b"type: [")
    concept.write_bytes(malformed)
    scripted.consolidations["entity"] = _reply(
        {"description": "New entity", "content": "Entity prose."}
    )
    result = _invoke(kb_dir, "consolidate", "--all", "--yes")
    assert result.exit_code == 1, result.output
    assert "[ERROR] Consolidation failed: Invalid YAML" in result.output
    assert "[OK] entities/alpha" in result.output
    assert "consolidated 1, skipped 0, failed 1" in result.output
    assert scripted.consolidation_calls == ["entity"]
    assert concept.read_bytes() == malformed
    assert "Entity prose." in _topic(kb_dir, "entities").read_text()

    concept.write_bytes(original)
    scripted.consolidations["concept"] = _reply(
        {"description": "Recovered", "content": "Concept prose."}
    )
    assert _invoke(kb_dir, "consolidate", "alpha").exit_code == 0
    skipped = _invoke(kb_dir, "consolidate", "alpha")
    assert skipped.exit_code == 0, skipped.output
    assert "[SKIP] concepts/alpha (no pending notes)." in skipped.output
    assert scripted.consolidation_calls == ["entity", "concept"]


@pytest.mark.parametrize("bad_description", [{"key": "value"}, ["line"], "one\ntwo"])
def test_invalid_replacement_description_preserves_metadata(kb_dir, scripted, bad_description):
    for doc in ("a", "b", "c"):
        _add(kb_dir, doc)
    concept = _topic(kb_dir, "concepts")
    metadata = frontmatter.split(concept.read_text())[0]
    index_before = (kb_dir / "wiki" / "index.md").read_bytes()
    scripted.consolidations["concept"] = _reply(
        {"description": bad_description, "content": "Good prose."}
    )
    result = _invoke(kb_dir, "consolidate", "alpha")
    assert result.exit_code == 0, result.output
    assert frontmatter.split(concept.read_text())[0] == metadata
    assert (kb_dir / "wiki" / "index.md").read_bytes() == index_before


def test_v2_summary_truncation_keeps_v1(kb_dir, scripted):
    scripted.summary_rewrite = _reply("Partial v2 rewrite.", "length")
    _add(kb_dir, "a")
    summary = (kb_dir / "wiki" / "summaries" / "a.md").read_text()
    assert "Intact v1 facts for a." in summary
    assert "Partial v2" not in summary


@pytest.mark.parametrize("mode", ["append", "rewrite"])
@pytest.mark.parametrize("fault", ["first_page", "clear_store", "index"])
def test_failed_promotion_restores_bytes_and_retry_promotes_once(kb_dir, scripted, mode, fault):
    with (kb_dir / ".openkb" / "config.yaml").open("a") as config:
        config.write(f"concept_update_mode: {mode}\n")
    _add(kb_dir, "a")
    _add(kb_dir, "b")
    prior = _state(kb_dir)
    write = compiler.atomic_write_text
    remove = PendingTopicsStore.remove

    def after_first_page(path, text):
        write(path, text)
        if path == _topic(kb_dir, "concepts"):
            assert len(frontmatter.parse_required(path.read_text())["sources"]) == 3
            assert all(f"[[summaries/{doc}]]" in text for doc in ("a", "b", "c"))
            assert "[[ghost]]" not in text
            raise OSError("fault after first page write")

    def after_clear(store, kind, slug):
        remove(store, kind, slug)
        raise OSError("fault after clearing pending notes")

    faults = {
        "first_page": patch.object(compiler, "atomic_write_text", side_effect=after_first_page),
        "clear_store": patch.object(PendingTopicsStore, "remove", new=after_clear),
        "index": patch.object(compiler, "_update_index", side_effect=OSError("fault before index")),
    }
    with faults[fault], patch("openkb.cli.time.sleep"):
        result = _add(kb_dir, "c", fails=True)
    assert "fault" in result.output
    assert _state(kb_dir) == prior
    assert list((kb_dir / ".openkb" / "journal").glob("*.json")) == []
    _add(kb_dir, "c")
    index = (kb_dir / "wiki" / "index.md").read_text()
    for kind in ("concepts", "entities"):
        assert index.count(f"[[{kind}/alpha]]") == 1
        for doc in ("a", "b", "c"):
            assert f"[[{kind}/alpha]]" in (kb_dir / "wiki" / "summaries" / f"{doc}.md").read_text()
        assert PendingTopicsStore(pending_topics_path(kb_dir)).get(kind, "alpha") is None


def test_retry_starts_from_baseline_and_failed_rewrite_is_not_a_link_target(kb_dir, scripted):
    with (kb_dir / ".openkb" / "config.yaml").open("a") as config:
        config.write("concept_update_mode: rewrite\n")
    for doc in ("a", "b"):
        _add(kb_dir, doc)
    scripted.summary_rewrite = _reply("Links to [[concepts/alpha]] and [[entities/alpha]].")
    finish_index = compiler._update_index
    tries = 0

    def retry_with_concept_failure(*args, **kwargs):
        nonlocal tries
        tries += 1
        if tries == 1:
            assert _topic(kb_dir, "concepts").exists()
            scripted.fail_concept_rewrite = True
            raise OSError("retry after publication")
        return finish_index(*args, **kwargs)

    with (
        patch.object(compiler, "_update_index", side_effect=retry_with_concept_failure),
        patch("openkb.cli.time.sleep"),
    ):
        _add(kb_dir, "c")
    assert tries == 2
    assert not _topic(kb_dir, "concepts").exists()
    assert _topic(kb_dir, "entities").exists()
    assert find_broken_links(kb_dir / "wiki") == []
    assert PendingTopicsStore(pending_topics_path(kb_dir)).note_count("concepts", "alpha") == 3


@pytest.mark.parametrize("buffered", [False, True])
def test_next_exclusive_cli_recovers_abrupt_add_exit(kb_dir, scripted, buffered):
    if buffered:
        _add(kb_dir, "a")
        _add(kb_dir, "b")
    before = _state(kb_dir)
    incoming = _input(kb_dir, "c")
    # Exit the process without unwinding either the compiler or the mutation coordinator.
    code = """
import os, runpy, sys
from pathlib import Path
ns = runpy.run_path(sys.argv[1])
model = ns['ScriptedModel']()
compiler = ns['compiler']
compiler.litellm.completion = model.complete
compiler.litellm.acompletion = model.acomplete
compiler._update_index = lambda *args, **kwargs: os._exit(73)
ns['_invoke'](Path(sys.argv[2]), 'add', sys.argv[3])
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(Path(__file__).resolve()), str(kb_dir), str(incoming)],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert completed.returncode == 73, completed.stdout + completed.stderr
    assert pending_topics_path(kb_dir).exists()
    assert list((kb_dir / ".openkb" / "journal").glob("*.json"))
    assert _topic(kb_dir, "concepts").exists() is buffered
    result = _invoke(kb_dir, "remove", "c", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "No document matching 'c'" in result.output
    assert _state(kb_dir) == before
    _add(kb_dir, "c")


def test_cloud_import_rolls_back_new_pending_store(kb_dir, scripted):
    cloud = CloudImportData(
        doc_id="cloud-id",
        doc_name="cloud-source",
        cloud_name="cloud source.pdf",
        tree={"structure": []},
        all_pages=[],
        description="Cloud brief",
    )
    before = _state(kb_dir)
    with (
        patch("openkb.cli.prepare_cloud_import", return_value=cloud),
        patch.object(compiler, "_update_index", side_effect=OSError("cloud index failure")),
        patch("openkb.cli.time.sleep"),
    ):
        result = _invoke(kb_dir, "add", "--from-pageindex-cloud", "cloud-id")
    assert result.exit_code == 1, result.output
    assert "cloud index failure" in result.output
    assert _state(kb_dir) == before


def test_remove_purge_promote_consolidate_lint_round_trip(kb_dir, scripted):
    wiki = kb_dir / "wiki"
    for doc in ("a", "b"):
        _add(kb_dir, doc)
    pending = pending_topics_path(kb_dir)
    scripted.notes["a"] = "Updated text from a.\n\nSecond paragraph."
    recompiled = _invoke(kb_dir, "recompile", "a.md")
    assert "recompiled 1" in recompiled.output
    store = PendingTopicsStore(pending)
    for kind in ("concepts", "entities"):
        notes = store.notes(kind, "alpha")
        assert [note["doc_name"] for note in notes] == ["a", "b"]
        assert notes[0]["note"] == scripted.notes["a"]
        store.add_note(kind, "one-off", "private brief", "a", "summaries/a.md", "Only a.")
    baseline = _state(kb_dir)
    preview = _invoke(kb_dir, "remove", "a.md", "--dry-run")
    assert preview.exit_code == 0, preview.output
    assert "pending_topics.json  (purge 4 note(s))" in preview.output
    assert _state(kb_dir) == baseline

    with patch.object(compiler, "remove_doc_from_index", side_effect=OSError("remove fault")):
        failed = _invoke(kb_dir, "remove", "a.md", "--yes")
    assert failed.exit_code == 1
    assert _state(kb_dir) == baseline
    removed = _invoke(kb_dir, "remove", "a.md", "--yes")
    assert removed.exit_code == 0, removed.output
    assert "[OK] a.md removed" in removed.output
    store = PendingTopicsStore(pending)
    for kind in ("concepts", "entities"):
        assert store.get(kind, "one-off") is None
        assert [n["doc_name"] for n in store.notes(kind, "alpha")] == ["b"]
    _add(kb_dir, "c")
    assert not _topic(kb_dir, "concepts").exists()
    _add(kb_dir, "d")
    for kind in ("concepts", "entities"):
        text = _topic(kb_dir, kind).read_text()
        assert frontmatter.parse_required(text)["sources"] == [f"summaries/{d}.md" for d in "dcb"]
        assert "Note from a" not in text and "[[ghost]]" not in text
        for doc in "bcd":
            assert text.count(f"Note from {doc}.") == 1
            summary = (wiki / "summaries" / f"{doc}.md").read_text()
            assert summary.count(f"[[{kind}/alpha]]") == 1

    topic = _topic(kb_dir, "concepts")
    fm, body = frontmatter.split(topic.read_text())
    fm = re.sub(
        r"^description:.*$", "description: |\n  Old first line.\n  Old second line.", fm, flags=re.M
    )
    topic.write_text(fm.removesuffix("---\n") + "custom:\n  keep: yes\n---\n" + body)
    for kind in ("concept", "entity"):
        scripted.consolidations[kind] = _reply(
            {
                "description": f"New {kind} brief",
                "content": "---\ntype: ignored\n---\n\nConsolidated facts.",
            }
        )
    preview = _invoke(kb_dir, "consolidate", "--all", "--dry-run")
    assert "Would consolidate 2 page(s):" in preview.output
    assert scripted.consolidation_calls == []
    result = _invoke(kb_dir, "consolidate", "--all", "--yes")
    assert result.exit_code == 0, result.output
    index = (wiki / "index.md").read_text()
    assert "- [[concepts/alpha]] — New concept brief" in index
    assert "- [[entities/alpha]] (organization) — New entity brief" in index
    assert frontmatter.parse_required(topic.read_text())["custom"] == {"keep": True}
    for kind in ("concepts", "entities"):
        text = _topic(kb_dir, kind).read_text()
        assert "## Notes" not in text
        assert "Old second line." not in text
        assert "Consolidated facts." in text
        assert all(f"[[summaries/{doc}]]" in text for doc in "bcd")

    exploration = wiki / "explorations" / "test.md"
    exploration.write_text("[[alpha]] and [[entities/alpha]] and [[missing-page|a ghost]].\n")
    ghosts = find_broken_links(wiki)
    assert len(ghosts) == 1 and "missing-page" in ghosts[0]
    fixed = _invoke(kb_dir, "lint", "--fix")
    assert fixed.exit_code == 0, fixed.output
    assert exploration.read_text() == "[[alpha]] and [[entities/alpha]] and a ghost.\n"
    assert find_broken_links(wiki) == []

    exploration.write_text(exploration.read_text() + "Source [[summaries/b]].\n")
    result = _invoke(kb_dir, "remove", "b.md", "--yes")
    assert "[OK] b.md removed" in result.output
    for kind in ("concepts", "entities"):
        text = _topic(kb_dir, kind).read_text()
        assert frontmatter.parse_required(text)["sources"] == ["summaries/d.md", "summaries/c.md"]
        assert "[[summaries/b]]" not in text
    assert find_broken_links(wiki) == ["Broken link [[summaries/b]] in explorations/test.md"]


def test_malformed_pending_store_is_preserved(kb_dir, scripted):
    _add(kb_dir, "a")
    pending_topics_path(kb_dir).write_bytes(b'{"concepts":null}')
    before = _state(kb_dir)
    _add(kb_dir, "b", fails=True)
    assert _invoke(kb_dir, "remove", "a.md", "--yes").exit_code == 1
    assert _state(kb_dir) == before


def test_consolidation_index_failure_rolls_back_page(kb_dir, scripted):
    for doc in "abc":
        _add(kb_dir, doc)
    page = _topic(kb_dir, "concepts")
    index = kb_dir / "wiki" / "index.md"
    before = page.read_bytes(), index.read_bytes()
    write = consolidator.atomic_write_text

    def fail_after_index_write(path, text):
        write(path, text)
        if path == index:
            raise OSError("index write fault")

    scripted.consolidations["concept"] = _reply({"description": "New", "content": "New prose."})
    with patch.object(consolidator, "atomic_write_text", side_effect=fail_after_index_write):
        result = _invoke(kb_dir, "consolidate", "alpha")
    assert result.exit_code == 1, result.output
    assert "index write fault" in result.output
    assert (page.read_bytes(), index.read_bytes()) == before
