"""
Unit tests for validator.py -- checks that WELL-FORMED-BUT-BAD-VALUE
records get correctly rejected. This is distinct from test_parser.py,
which only checks structural (regex) failures.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validator import validate_record


def make_parsed(**overrides):
    base = {
        "ip": "127.0.0.1",
        "timestamp": "10/Oct/2023:13:55:36 -0700",
        "method": "GET",
        "path": "/index.html",
        "protocol": "HTTP/1.1",
        "status": "200",
        "size": "2326",
    }
    base.update(overrides)
    return base


def test_valid_record_passes():
    record = validate_record(make_parsed())
    assert record.status == 200
    assert record.size == 2326
    assert record.method == "GET"


def test_rejects_out_of_range_status():
    with pytest.raises(ValidationError, match="out of valid HTTP range"):
        validate_record(make_parsed(status="999"))


def test_rejects_negative_size():
    with pytest.raises(ValidationError, match="negative response size"):
        validate_record(make_parsed(size="-5"))


def test_rejects_unparseable_timestamp():
    with pytest.raises(ValidationError, match="unparseable timestamp"):
        validate_record(make_parsed(timestamp="NOT-A-DATE"))


def test_rejects_unknown_method():
    with pytest.raises(ValidationError, match="unknown HTTP method"):
        validate_record(make_parsed(method="WEIRDMETHODONLY"))


def test_converts_types_correctly():
    record = validate_record(make_parsed())
    assert isinstance(record.status, int)
    assert isinstance(record.size, int)
