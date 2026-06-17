"""Unit tests for pure log-slicing helpers."""

from semaphore_mcp.output_utils import (
    CHANGED_RE,
    FAILURE_RE,
    clamp,
    extract_blocks,
    extract_recap,
    search,
    split_lines,
    strip_ansi,
    window,
)

SAMPLE = "\n".join(
    [
        "PLAY [all] ***",
        "TASK [common : install] ***",
        "ok: [hostA]",
        "TASK [web : deploy] ***",
        "changed: [hostA]",
        'fatal: [hostB]: FAILED! => {"msg": "boom"}',
        "...some trailing detail...",
        "PLAY RECAP ***",
        "hostA : ok=2 changed=1 failed=0",
        "hostB : ok=1 changed=0 failed=1",
    ]
)


def test_strip_ansi():
    assert strip_ansi("\x1b[31mfatal:\x1b[0m x") == "fatal: x"


def test_split_lines_drops_one_trailing_empty():
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\nb") == ["a", "b"]


def test_clamp():
    assert clamp(5000, 1, 2000) == 2000
    assert clamp(0, 1, 2000) == 1
    assert clamp(50, 1, 2000) == 50


def test_window_tail():
    lines = [str(i) for i in range(10)]
    w = window(lines, "tail", 3)
    assert w["lines"] == ["7", "8", "9"]
    assert w["returned_range"] == [7, 10]
    assert w["truncated"] is True
    assert w["next_offset"] is None


def test_window_head_and_range_paging():
    lines = [str(i) for i in range(10)]
    h = window(lines, "head", 4)
    assert h["lines"] == ["0", "1", "2", "3"]
    assert h["next_offset"] == 4
    r = window(lines, "range", 4, offset=h["next_offset"])
    assert r["lines"] == ["4", "5", "6", "7"]
    assert r["next_offset"] == 8


def test_window_not_truncated_when_fits():
    lines = ["a", "b"]
    w = window(lines, "tail", 200)
    assert w["truncated"] is False
    assert w["next_offset"] is None


def test_search_substring_with_context_and_match_flag():
    lines = split_lines(SAMPLE)
    res = search(lines, "fatal:", context=1)
    texts = [e["text"] for e in res["entries"]]
    assert res["match_count"] == 1
    assert any("fatal: [hostB]" in t for t in texts)
    assert any(e["is_match"] for e in res["entries"])


def test_search_bad_regex_returns_error_not_raise():
    res = search(["x"], "(", regex=True)
    assert res["match_count"] == 0
    assert "error" in res


def test_search_caps_emitted_lines():
    lines = ["match"] * 50
    res = search(lines, "match", context=0, max_lines=10)
    assert res["returned_lines"] == 10
    assert res["truncated"] is True


def test_extract_blocks_anchors_to_task_header():
    lines = split_lines(SAMPLE)
    blocks, total = extract_blocks(lines, FAILURE_RE)
    assert total == 1
    assert blocks[0]["task_header"].startswith("TASK [web : deploy]")
    assert blocks[0]["host"] == "hostB"
    assert any("boom" in ln for ln in blocks[0]["lines"])


def test_extract_blocks_caps_block_count():
    lines = ["TASK [t] ***", "fatal: [h]: x"] * 30
    blocks, total = extract_blocks(lines, FAILURE_RE, max_blocks=5)
    assert total == 30
    assert len(blocks) == 5


def test_changed_marker_matches_changed_lines():
    lines = split_lines(SAMPLE)
    _, total = extract_blocks(lines, CHANGED_RE)
    assert total == 1


def test_extract_recap():
    recap = extract_recap(split_lines(SAMPLE))
    assert recap[0].startswith("PLAY RECAP")
    assert any("failed=1" in ln for ln in recap)
