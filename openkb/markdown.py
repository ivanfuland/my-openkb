"""Line ranges for editing Markdown while preserving fenced code examples."""

from collections.abc import Iterator

from markdown_it import MarkdownIt

_BLOCKS = MarkdownIt("commonmark").disable("inline")


def unfenced_line_ranges(lines: list[str]) -> Iterator[tuple[int, int]]:
    """Yield half-open ranges excluding fenced blocks and their delimiters."""
    start = 0
    text = "\n".join(line.rstrip("\r\n") for line in lines)
    if "```" in text or "~~~" in text:
        for token in _BLOCKS.parse(text):
            if token.type != "fence" or token.map is None:
                continue
            fence_start, fence_end = token.map
            if start < fence_start:
                yield start, fence_start
            start = fence_end
    if start < len(lines):
        yield start, len(lines)
