"""Shared helpers for the YAML frontmatter blocks of OpenKB wiki pages.

Single source of truth for building, splitting, parsing, and mutating the
``---`` frontmatter used by summaries / concepts / entities. The delimiters
must occupy entire lines so a value containing dashes isn't truncated.
"""

from __future__ import annotations

import json
import re

import yaml


def kv_line(key: str, value: str) -> str:
    """Render ``key: "value"`` with the value JSON-quoted (always single-line).

    JSON strings are a strict subset of YAML: always single-line, always
    correctly escaped (newlines, quotes, colons, control chars), and never
    auto-promoted to a block scalar.
    """
    return f"{key}: {json.dumps(value, ensure_ascii=False)}"


def list_line(key: str, items) -> str:
    """Render ``key: ["a", "b"]`` as JSON-style YAML (always single-line)."""
    return f"{key}: {json.dumps(list(items), ensure_ascii=False)}"


def block(lines: list[str]) -> str:
    """Assemble a complete frontmatter block (with delimiters + trailing blank)."""
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def parse_list_value(line: str) -> list[str] | None:
    """Parse the right-hand side of ``key: [...]`` into a list of strings.

    Returns ``None`` when the value cannot be interpreted as a list — callers
    treat that as "leave the frontmatter alone".
    """
    colon = line.find(":")
    if colon == -1:
        return None
    try:
        parsed = yaml.safe_load(line[colon + 1 :])
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, list):
        return None
    return [str(x) for x in parsed]


_OPENING_FENCE = re.compile(r"\A---[ \t]*\r?\n")
_CLOSING_FENCE = re.compile(r"^---[ \t]*(?:\r?\n|\Z)", re.MULTILINE)


def split(text: str) -> tuple[str, str] | None:
    """Split a fenced page losslessly into ``(frontmatter_block, body)``."""
    opening = _OPENING_FENCE.match(text)
    if opening is None:
        return None
    closing = _CLOSING_FENCE.search(text, opening.end())
    if closing is None:
        return None
    return text[: closing.end()], text[closing.end() :]


def parse_required(text: str) -> dict:
    """Read a fenced YAML mapping, raising before an unsafe page rewrite."""
    parts = split(text)
    if parts is None:
        raise ValueError("Missing or unterminated YAML frontmatter")
    lines = parts[0].splitlines(keepends=True)
    try:
        data = yaml.safe_load("".join(lines[1:-1]))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("YAML frontmatter must be a mapping")
    return data


def parse(text: str) -> dict:
    """Return the frontmatter as a dict (``{}`` when absent or malformed)."""
    try:
        return parse_required(text)
    except ValueError:
        return {}


def strip_model_frontmatter(text: str) -> str:
    """Discard model-supplied metadata before checking the replacement body."""
    text = text.lstrip("\r\n")
    while (parts := split(text)) is not None:
        text = parts[1].lstrip("\r\n")
    if _OPENING_FENCE.match(text):
        raise ValueError("Model response has unterminated YAML frontmatter")
    return text


def single_line_description(value: object) -> str:
    """Normalize a model brief, omitting values unsuitable for an index row."""
    if isinstance(value, str) and value and value.splitlines() == [value] and "\x00" not in value:
        return value.strip()
    return ""


def set_line(fm_block: str, key: str, value: str) -> str:
    """Replace a top-level scalar (including its indented continuations)."""
    line = kv_line(key, value)
    key_pattern = re.escape(key)
    key_start = rf'''^(?:{key_pattern}|"{key_pattern}"|'{key_pattern}'):'''
    continuations = r"[^\r\n]*(?:\r?\n(?:[ \t]*\r?\n)*[ \t]+[^\r\n]*)*"
    pattern = key_start + continuations
    updated, count = re.subn(pattern, lambda _m: line, fm_block, count=1, flags=re.MULTILINE)
    if count:
        return updated
    return _OPENING_FENCE.sub(lambda m: f"{m[0]}{line}\n", fm_block, count=1)


def drop_line(fm_block: str, key: str) -> str:
    """Remove any ``key:`` line from a frontmatter block (no-op if absent)."""
    return re.sub(rf"^{re.escape(key)}:.*\n?", "", fm_block, flags=re.MULTILINE)
