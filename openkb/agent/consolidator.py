"""Consolidation backend for the ``openkb consolidate`` command.

See the command's help for the user-facing rewrite and selection behavior.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from openkb import frontmatter
from openkb.agent.compiler_notes import _NOTES_HEADING
from openkb.lint import list_existing_wiki_targets, strip_ghost_wikilinks
from openkb.locks import atomic_write_text
from openkb.mutation import snapshot_paths
from openkb.schema import INDEX_SEED, get_agents_md

logger = logging.getLogger(__name__)

_CONSOLIDATE_CONCEPT_USER = """\
Consolidate the concept page: {title}

Existing prose on this page (may be empty if this is the first consolidation):
{existing_content}

Accumulated notes to fold in, newest first (each tied to a source document):
{notes_content}

Rewrite the ENTIRE page as a single, coherent Markdown page that:
- Preserves every distinct fact from both the existing prose and the notes.
- If notes conflict with each other or with the existing prose, describe the \
conflict directly in the text (which source said what, and when) instead of \
silently picking one side.
- Uses [[wikilinks]] to related concepts/entities, per the whitelist message \
above.
- Does NOT include a "## Notes" section or any raw note lines — fold their \
content into the prose instead.

Return a JSON object with two keys:
- "description": A single sentence (under 100 chars) defining this concept
- "content": The rewritten full concept page in Markdown

Return ONLY valid JSON, no fences.
"""

_CONSOLIDATE_ENTITY_USER = """\
Consolidate the entity page: {title} (type: {type})

Existing prose on this page (may be empty if this is the first consolidation):
{existing_content}

Accumulated notes to fold in, newest first (each tied to a source document):
{notes_content}

Rewrite the ENTIRE page as a single, coherent Markdown page that:
- Preserves every distinct fact from both the existing prose and the notes.
- If notes conflict with each other or with the existing prose, describe the \
conflict directly in the text (which source said what, and when) instead of \
silently picking one side.
- Uses [[wikilinks]] to related concepts/entities, per the whitelist message \
above.
- Does NOT include a "## Notes" section or any raw note lines — fold their \
content into the prose instead.

Return a JSON object with two keys:
- "description": A single sentence (under 100 chars) identifying this entity
- "content": The rewritten full entity page in Markdown

Return ONLY valid JSON, no fences.
"""


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def _split_notes(body: str) -> tuple[str, str]:
    """Split a page body into ``(existing_prose, notes_content)``.

    ``notes_content`` is empty when there is no ``## Notes`` heading (nothing
    pending) — callers treat that as "skip, no notes to consolidate".
    """
    lines = body.split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.strip() == _NOTES_HEADING), None)
    if idx is None:
        return body.strip(), ""
    existing = "\n".join(lines[:idx]).strip()
    notes = "\n".join(lines[idx + 1 :]).strip()
    return existing, notes


def count_pending_notes(text: str) -> int:
    """Count ``## Notes`` bullet lines in a page's raw text (0 if none)."""
    parts = frontmatter.split(text)
    _, notes = _split_notes(parts[1] if parts is not None else text)
    if not notes:
        return 0
    return sum(1 for ln in notes.split("\n") if ln.lstrip().startswith("- **"))


def find_consolidation_candidates(wiki_dir: Path, min_notes: int = 1) -> list[tuple[str, str, int]]:
    """Return ``(page_dir, slug, note_count)`` for pages with pending notes.

    ``page_dir`` is ``"concepts"`` or ``"entities"``. Only pages with at least
    ``min_notes`` pending note lines are included.
    """
    candidates: list[tuple[str, str, int]] = []
    for page_dir in ("concepts", "entities"):
        dir_path = wiki_dir / page_dir
        if not dir_path.is_dir():
            continue
        for path in sorted(dir_path.glob("*.md")):
            count = count_pending_notes(path.read_text(encoding="utf-8"))
            if count >= min_notes:
                candidates.append((page_dir, path.stem, count))
    return candidates


def resolve_page(wiki_dir: Path, name: str) -> list[tuple[str, str]]:
    """Resolve ``name`` to ``[(page_dir, slug)]`` matches (exact slug first).

    Returns an empty list when nothing matches, or more than one entry when
    ``name`` is an ambiguous substring across concepts/entities — callers
    decide how to report each case.
    """
    for page_dir in ("concepts", "entities"):
        if (wiki_dir / page_dir / f"{name}.md").exists():
            return [(page_dir, name)]

    matches: list[tuple[str, str]] = []
    for page_dir in ("concepts", "entities"):
        dir_path = wiki_dir / page_dir
        if not dir_path.is_dir():
            continue
        for path in sorted(dir_path.glob("*.md")):
            if name.lower() in path.stem.lower():
                matches.append((page_dir, path.stem))
    return matches


async def consolidate_page(
    wiki_dir: Path, page_dir: str, slug: str, model: str, language: str = "en"
) -> bool:
    """Fold ``page_dir/slug``'s pending notes into curated prose.

    Returns ``False`` without an LLM call when the Notes section is absent
    or empty. Frontmatter validation, generation, and publication can raise.
    An accepted description change journals the page and index together so
    a failed index write can restore both files.
    """
    from openkb.agent import compiler as _compiler

    path = wiki_dir / page_dir / f"{slug}.md"
    text = path.read_text(encoding="utf-8")
    parts = frontmatter.split(text)
    existing_content, notes_content = _split_notes(parts[1] if parts is not None else text)
    if not notes_content:
        return False

    fm = frontmatter.parse_required(text)
    assert parts is not None  # parse_required checked the delimiters
    fm_block = parts[0]
    title = _title_from_slug(slug)
    known_targets = list_existing_wiki_targets(wiki_dir)
    known_targets_str = _compiler._format_known_targets(known_targets)

    system_msg = {
        "role": "system",
        "content": _compiler._SYSTEM_TEMPLATE.format(
            schema_md=get_agents_md(wiki_dir),
            language=language,
        ),
    }
    known_targets_msg = {
        "role": "user",
        "content": _compiler._KNOWN_TARGETS_USER.format(known_targets=known_targets_str),
    }
    if page_dir == "entities":
        etype = fm.get("type", "other")
        user_content = _CONSOLIDATE_ENTITY_USER.format(
            title=title,
            type=etype,
            existing_content=existing_content or "(none — first consolidation for this page)",
            notes_content=notes_content,
        )
    else:
        user_content = _CONSOLIDATE_CONCEPT_USER.format(
            title=title,
            existing_content=existing_content or "(none — first consolidation for this page)",
            notes_content=notes_content,
        )

    raw = await _compiler._llm_call_page_async(
        model,
        [system_msg, known_targets_msg, {"role": "user", "content": user_content}],
        f"consolidate: {page_dir}/{slug}",
        response_format=_compiler._JSON_RESPONSE_FORMAT,
    )
    description, content, _obj = _compiler._page_fields(raw)
    clean = frontmatter.strip_model_frontmatter(content)
    cleaned, ghosts = strip_ghost_wikilinks(clean, known_targets)
    _compiler._require_nonempty_content(cleaned, slug)
    if ghosts:
        logger.info(
            "stripped %d ghost wikilink(s) from consolidated %s/%s: %s",
            len(ghosts),
            page_dir,
            slug,
            ghosts[:5],
        )

    if description:
        fm_block = frontmatter.set_line(fm_block, "description", description)
    replacement = fm_block + "\n" + cleaned
    expected_fm = fm | ({"description": description} if description else {})
    if frontmatter.parse_required(replacement) != expected_fm:
        raise ValueError("Consolidation could not preserve the page's frontmatter")

    if not description:
        atomic_write_text(path, replacement)
        return True

    # Publish the page and its index row together. This block has no awaits,
    # so concurrent consolidations each read the latest index before editing it.
    index_path = wiki_dir / "index.md"
    index = index_path.read_text(encoding="utf-8") if index_path.exists() else INDEX_SEED
    lines = index.split("\n")
    entity_type = (
        frontmatter.single_line_description(fm.get("type")) if page_dir == "entities" else ""
    )
    _compiler._upsert_topic_index_entry(lines, page_dir, slug, description, entity_type.lower())
    snapshot = snapshot_paths(wiki_dir.parent, [path, index_path], operation="consolidate")
    try:
        atomic_write_text(path, replacement)
        atomic_write_text(index_path, "\n".join(lines))
        snapshot.mark_committed()
    except BaseException:
        if snapshot.rollback_best_effort() is None:
            snapshot.discard_best_effort()
        raise
    snapshot.discard_best_effort()
    return True


async def consolidate_pages(
    wiki_dir: Path,
    targets: list[tuple[str, str, int]],
    model: str,
    language: str,
    max_concurrency: int,
) -> list[tuple[bool | None, Exception | None, float]]:
    """Consolidate several pages concurrently, bounded by ``max_concurrency``.

    Mirrors the concept/entity generation concurrency model used during
    ingest (``openkb.agent.compiler._compile_concepts``). Returns one
    ``(ok, error, elapsed_seconds)`` per target, in the same order as
    ``targets`` regardless of completion order — a per-page exception is
    captured here rather than propagated, so one page's failure never
    aborts the batch (mirrors ``recompile``).
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(page_dir: str, slug: str) -> tuple[bool | None, Exception | None, float]:
        start = time.time()
        async with semaphore:
            try:
                ok = await consolidate_page(wiki_dir, page_dir, slug, model, language=language)
            except Exception as exc:
                return None, exc, time.time() - start
        return ok, None, time.time() - start

    from openkb.agent.compiler import _close_async_llm_clients

    try:
        return await asyncio.gather(*(_run_one(page_dir, slug) for page_dir, slug, _ in targets))
    finally:
        await _close_async_llm_clients()
