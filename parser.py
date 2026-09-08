"""
parser.py

Turns ONE raw log line into structured fields using a regex.

Why regex here: Common Log Format is fixed-structure but not delimited
by commas/tabs like a CSV, so splitting on whitespace breaks the moment
a path or timestamp contains a space. A regex with named groups is the
standard, reliable way to pull fields out of this kind of text.

This module intentionally does ONE thing: parse a line, or raise
ValueError with a clear reason if it can't. Validation of the parsed
VALUES (e.g. "is this status code sane?") is a separate concern, handled
in validator.py with Pydantic. Keeping these separate means each piece
is small enough to unit test on its own -- which is exactly what
tests/test_parser.py does.
"""

import re

# Named groups make the parsed result self-documenting: match.groupdict()
# returns {"ip": ..., "timestamp": ..., "method": ...} directly.
CLF_PATTERN = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ '
    r'\[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r'(?P<status>\d{3}) '
    r'(?P<size>\d+)$'
)


def parse_line(raw_line: str) -> dict:
    """
    Parse a single raw log line into a dict of string fields.

    Raises ValueError with a human-readable reason if the line doesn't
    match the expected format. Callers (pipeline.py) catch this and route
    the line to the "malformed" bucket instead of crashing the whole run --
    one bad line should never take down processing of the other 999,999.
    """
    line = raw_line.strip()
    if not line:
        raise ValueError("blank line")

    match = CLF_PATTERN.match(line)
    if not match:
        raise ValueError("line does not match expected log format")

    return match.groupdict()


if __name__ == "__main__":
    # Quick manual sanity check when running this file directly
    sample = '127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326'
    print(parse_line(sample))
