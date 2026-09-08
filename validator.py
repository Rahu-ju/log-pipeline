"""
validator.py

parser.py gives us a dict of STRINGS pulled out of the raw text.
This module is where we answer: "are these values actually sane, and can
we convert them to real types (int, datetime)?"

We use Pydantic because it does both jobs in one step:
  1. Type conversion (status: "200" -> 200)
  2. Validation (status must be a plausible HTTP code, size can't be negative)
and it raises a single clear ValidationError listing every field that
failed, rather than us hand-writing a pile of if/else checks.

Splitting parsing (parser.py) from validation (this file) matters because
they fail for different reasons: a line can be perfectly well-FORMED
(matches the regex) but still contain a nonsense VALUE (status "999").
Keeping them separate makes each failure reason precise, which is exactly
what "handle malformed, duplicate, and invalid records with appropriate
error tracking" is asking for -- you want to know WHY a record was
rejected, not just THAT it was.
"""

from datetime import datetime
from pydantic import BaseModel, field_validator


class LogRecord(BaseModel):
    ip: str
    timestamp: datetime
    method: str
    path: str
    protocol: str
    status: int
    size: int

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_clf_timestamp(cls, value: str) -> datetime:
        # Raw format looks like: 10/Oct/2023:13:55:36 -0700
        try:
            return datetime.strptime(value, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError as e:
            raise ValueError(f"unparseable timestamp '{value}': {e}")

    @field_validator("status")
    @classmethod
    def status_must_be_valid_http_code(cls, value: int) -> int:
        if not (100 <= value <= 599):
            raise ValueError(f"status code {value} out of valid HTTP range")
        return value

    @field_validator("size")
    @classmethod
    def size_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"negative response size {value}")
        return value

    @field_validator("method")
    @classmethod
    def method_must_be_known(cls, value: str) -> str:
        known = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if value not in known:
            raise ValueError(f"unknown HTTP method '{value}'")
        return value


def validate_record(parsed: dict) -> LogRecord:
    """
    Convert+validate a parsed dict into a LogRecord.
    Raises pydantic.ValidationError on any failure -- caller decides
    what to do with rejected records (pipeline.py logs them).
    """
    return LogRecord(**parsed)


if __name__ == "__main__":
    from parser import parse_line

    good = '127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326'
    record = validate_record(parse_line(good))
    print(record)

    bad = '127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 999 2326'
    try:
        validate_record(parse_line(bad))
    except Exception as e:
        print("Rejected as expected:", e)
