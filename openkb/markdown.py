"""Line ranges for editing Markdown while preserving code blocks."""

from collections.abc import Iterator

from markdown_it import MarkdownIt
from markdown_it.token import Token

_BLOCKS = MarkdownIt("commonmark").disable("inline")


def _block_tokens(lines: list[str]) -> list[Token]:
    return _BLOCKS.parse("\n".join(line.rstrip("\r\n") for line in lines))


def non_code_line_ranges(lines: list[str]) -> Iterator[tuple[int, int]]:
    """Yield half-open ranges excluding fenced and indented code blocks."""
    start = 0
    for token in _block_tokens(lines):
        if token.type not in ("fence", "code_block") or token.map is None:
            continue
        code_start, code_end = token.map
        if start < code_start:
            yield start, code_start
        start = code_end
    if start < len(lines):
        yield start, len(lines)


def closing_fence_for_append(lines: list[str]) -> str | None:
    """Return a closing delimiter if an appended top-level heading would be fenced."""
    probe = [*lines, "", "#"]
    for token in _block_tokens(probe):
        if token.type == "fence" and token.map is not None and token.map[1] == len(probe):
            return token.markup
    return None
