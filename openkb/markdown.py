"""Line ranges for editing Markdown while preserving fenced code examples."""

from collections.abc import Iterator

from markdown_it import MarkdownIt

_BLOCKS = MarkdownIt("commonmark").disable("inline")


def _fenced_blocks(lines: list[str]) -> Iterator[tuple[int, int, str]]:
    text = "\n".join(line.rstrip("\r\n") for line in lines)
    if "```" in text or "~~~" in text:
        for token in _BLOCKS.parse(text):
            if token.type == "fence" and token.map is not None:
                fence_start, fence_end = token.map
                yield fence_start, fence_end, token.markup


def unfenced_line_ranges(lines: list[str]) -> Iterator[tuple[int, int]]:
    """Yield half-open ranges excluding fenced blocks and their delimiters."""
    start = 0
    for fence_start, fence_end, _ in _fenced_blocks(lines):
        if start < fence_start:
            yield start, fence_start
        start = fence_end
    if start < len(lines):
        yield start, len(lines)


def closing_fence_for_append(lines: list[str]) -> str | None:
    """Return a closing delimiter if an appended top-level heading would be fenced."""
    probe = [*lines, "", "#"]
    for _, end, delimiter in _fenced_blocks(probe):
        if end == len(probe):
            return delimiter
    return None
