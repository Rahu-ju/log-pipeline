"""
Unit tests for parser.py.

The point of testing the parser specifically: it's the piece most likely
to break in production, because real-world logs are never perfectly
uniform. These tests document exactly what "malformed" means for this
pipeline and pin down the parser's behavior so a future change can't
silently break it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from parser import parse_line


def test_parses_valid_line():
    line = '127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326'
    result = parse_line(line)
    assert result["ip"] == "127.0.0.1"
    assert result["method"] == "GET"
    assert result["path"] == "/index.html"
    assert result["status"] == "200"
    assert result["size"] == "2326"


def test_parses_post_request():
    line = '10.0.0.1 - - [01/Jan/2024:00:00:00 -0000] "POST /api/orders HTTP/1.1" 201 512'
    result = parse_line(line)
    assert result["method"] == "POST"
    assert result["status"] == "201"


def test_rejects_blank_line():
    with pytest.raises(ValueError, match="blank line"):
        parse_line("")


def test_rejects_whitespace_only_line():
    with pytest.raises(ValueError, match="blank line"):
        parse_line("   \n")


def test_rejects_garbage_text():
    with pytest.raises(ValueError, match="does not match expected log format"):
        parse_line("this is not a log line at all")


def test_rejects_missing_status_and_size():
    line = '10.0.0.5 - - [10/Jan/2024:00:00:00 -0000] "GET /missing-status HTTP/1.1"'
    with pytest.raises(ValueError):
        parse_line(line)


def test_rejects_truncated_line():
    line = '192.168.1.1 - - [10/Jan/2024:00:00:00 -0000] "WEIRDMETHODONLY" 200 100'
    with pytest.raises(ValueError):
        parse_line(line)
