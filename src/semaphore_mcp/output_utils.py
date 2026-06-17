"""Pure helpers for slicing and triaging Semaphore task output.

These functions operate on already-fetched log text so the windowing/triage
logic stays free of HTTP concerns and is unit-testable without mocks. The MCP
tools fetch the full output once server-side, then call these to return only a
bounded slice so the multi-MB payload never crosses the MCP transport.
"""

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TASK_HEADER_RE = re.compile(r"^\s*TASK \[")
_RECAP_RE = re.compile(r"^\s*PLAY RECAP")
_HOST_RE = re.compile(r"^\s*(?:fatal|failed|changed):\s*\[([^\]]+)\]", re.IGNORECASE)

# Anchored, case-insensitive markers exported for the tools.
FAILURE_RE = re.compile(r"^\s*(?:fatal|failed):", re.IGNORECASE)
CHANGED_RE = re.compile(r"^\s*changed:", re.IGNORECASE)


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR color codes from task output."""
    return _ANSI_RE.sub("", text)


def split_lines(raw: str) -> list[str]:
    """Split raw output into lines, dropping one trailing empty line."""
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def clamp(n: int, lo: int, hi: int) -> int:
    """Clamp n into the inclusive range [lo, hi]."""
    return max(lo, min(n, hi))


def window(lines: list[str], mode: str, max_lines: int, offset: int = 0) -> dict:
    """Return a bounded slice of lines.

    returned_range is half-open [start, end). next_offset is the index to pass
    back as offset with mode="range" to continue paging forward, or None once
    the end is reached.
    """
    total = len(lines)
    if mode == "head":
        start, end = 0, min(max_lines, total)
    elif mode == "tail":
        start, end = max(0, total - max_lines), total
    elif mode == "range":
        start = clamp(offset, 0, total)
        end = min(start + max_lines, total)
    else:
        raise ValueError(f"window() does not support mode={mode!r}")

    selected = lines[start:end]
    return {
        "returned_range": [start, end],
        "returned_lines": len(selected),
        "truncated": start > 0 or end < total,
        "next_offset": end if end < total else None,
        "lines": selected,
    }


def search(
    lines: list[str],
    pattern: str,
    regex: bool = False,
    context: int = 3,
    max_lines: int = 200,
) -> dict:
    """Find matching lines, returning matches plus context, capped at max_lines."""
    if regex:
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return {
                "match_count": 0,
                "returned_lines": 0,
                "truncated": False,
                "error": f"invalid regex: {exc}",
                "entries": [],
            }

        def is_match(s: str) -> bool:
            return compiled.search(s) is not None

    else:

        def is_match(s: str) -> bool:
            return pattern in s

    match_idx = [i for i, line in enumerate(lines) if is_match(strip_ansi(line))]
    match_set = set(match_idx)
    emit: set[int] = set()
    truncated = False

    for match_line in match_idx:
        lo = max(0, match_line - context)
        hi = min(len(lines), match_line + context + 1)
        for line_no in range(lo, hi):
            if line_no not in emit and len(emit) >= max_lines:
                truncated = True
                break
            emit.add(line_no)
        if truncated:
            break

    entries = [
        {
            "line": line_no,
            "text": strip_ansi(lines[line_no]),
            "is_match": line_no in match_set,
        }
        for line_no in sorted(emit)
    ]
    return {
        "match_count": len(match_idx),
        "returned_lines": len(entries),
        "truncated": truncated,
        "entries": entries,
    }


def extract_blocks(
    lines: list[str],
    marker: re.Pattern[str],
    max_blocks: int = 10,
    lines_per_block: int = 20,
) -> tuple[list[dict], int]:
    """Extract blocks around matching lines, tagged with the most recent TASK."""
    blocks: list[dict] = []
    total = 0
    last_header: str | None = None

    for i, line in enumerate(lines):
        clean = strip_ansi(line)
        if _TASK_HEADER_RE.match(clean):
            last_header = clean.strip()
        if marker.match(clean):
            total += 1
            if len(blocks) < max_blocks:
                end = min(len(lines), i + lines_per_block)
                host_match = _HOST_RE.match(clean)
                blocks.append(
                    {
                        "task_header": last_header,
                        "host": host_match.group(1) if host_match else None,
                        "line_range": [i, end],
                        "lines": [strip_ansi(x) for x in lines[i:end]],
                    }
                )

    return blocks, total


def extract_recap(lines: list[str], max_lines: int = 40) -> list[str]:
    """Return the PLAY RECAP block from the recap header forward, or []."""
    for i, line in enumerate(lines):
        if _RECAP_RE.match(strip_ansi(line)):
            end = min(len(lines), i + max_lines)
            return [strip_ansi(x) for x in lines[i:end]]
    return []
