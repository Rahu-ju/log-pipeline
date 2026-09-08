"""
pipeline.py

    -> stream line by line              (generator -- low memory)
    -> parse                            (parser.py)
    -> validate                         (validator.py)
    -> dedupe                           (hash-based)
    -> batch into DataFrames            (pandas)
    -> upsert into Postgres             (idempotent -- safe to rerun)
    -> log a run summary                (logging module)

Design of choices: 

1. STREAMING, NOT LOAD-EVERYTHING-THEN-PROCESS
   We never call file.readlines() or build one giant list of all records.
   `stream_lines()` is a generator -- it yields one line at a time, so
   memory use stays flat whether the file is 5,000 lines or 5,000,000.

2. IDEMPOTENT LOADING
   Each row gets a `record_hash` (SHA-256 of its raw line) as a unique
   key, and the Postgres insert uses ON CONFLICT DO NOTHING on that key.
   That means: if this script crashes halfway through a 10GB file and you
   just rerun it from the start, already-inserted rows are silently
   skipped instead of duplicated. This is what "restartable, idempotent
   data-processing workflow" means in practice -- you get to be lazy
   about crash recovery because the database enforces it for you.

3. BATCHING
   We don't insert one row at a time (slow: one round-trip per row) or
   wait for the whole file (memory-heavy). We accumulate BATCH_SIZE valid
   records, convert that chunk to a DataFrame, and insert the chunk. This
   is the standard shape of "batch processing."
"""

import hashlib
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from parser import parse_line
from validator import validate_record




logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("log_pipeline")

# Define db url and batch size
DB_URL = "postgresql+psycopg2://dbuser:dbpassword@db:5432/logdatabase"
BATCH_SIZE = 500

# Define db tabe and its column
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS access_log (
    record_hash   TEXT PRIMARY KEY,
    ip            TEXT NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    size          INTEGER NOT NULL
);
"""

CREATE_ERRORS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingestion_errors (
    id            SERIAL PRIMARY KEY,
    line_number   INTEGER NOT NULL,
    raw_line      TEXT NOT NULL,
    reason        TEXT NOT NULL,
    logged_at     TIMESTAMPTZ DEFAULT now()
);
"""


def stream_lines(path: str):
    """Generator: yields (line_number, raw_line) one at a time. Never
    holds the whole file in memory. This is what makes the pipeline
    safe to run on files far bigger than available RAM."""

    with open(path, "r") as f:
        for line_number, raw_line in enumerate(f, start=1):
            yield line_number, raw_line.rstrip("\n")


def record_hash(raw_line: str) -> str:
    """Generate unique key for a raw line. Used both to detect exact
    duplicates within a run and as the idempotency key in Postgres."""

    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()



def ensure_tables(engine):
    """ Connect with db and write those tables. """

    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        conn.execute(text(CREATE_ERRORS_TABLE_SQL))


def insert_batch(engine, df: pd.DataFrame) -> int:
    """
    Idempotent bulk insert: build one INSERT ... ON CONFLICT DO NOTHING
    statement and execute it with the whole batch at once (executemany-style)
    rather than row by row. Returns number of rows actually inserted
    (excludes ones skipped as already-existing).
    """
    if df.empty:
        return 0

    insert_sql = text("""
        INSERT INTO access_log (record_hash, ip, ts, method, path, status, size)
        VALUES (:record_hash, :ip, :ts, :method, :path, :status, :size)
        ON CONFLICT (record_hash) DO NOTHING
    """)
    records = df.to_dict(orient="records")
    with engine.begin() as conn:
        result = conn.execute(insert_sql, records)
        return result.rowcount


def log_errors(engine, errors: list[dict]) -> None:
    """ Insert error to the ingestion_errors table"""

    if not errors:
        return
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO ingestion_errors (line_number, raw_line, reason)
                     VALUES (:line_number, :raw_line, :reason)"""),
            errors,
        )


def run_pipeline(log_path: str) -> dict:

    # connect with db and create tables
    engine = create_engine(DB_URL)
    ensure_tables(engine)

    # Define some variables for statistic purpose
    stats = {"total_lines": 0, "valid": 0, "malformed": 0,
              "duplicate_in_run": 0, "inserted": 0, "skipped_existing": 0}

    seen_hashes: set[str] = set()
    batch_records: list[dict] = []
    batch_errors: list[dict] = []

    def flush():
        """ insert data to those tables otherwise empty the variables."""

        nonlocal batch_records, batch_errors
        if batch_records:
            df = pd.DataFrame(batch_records)
            inserted = insert_batch(engine, df)
            stats["inserted"] += inserted
            stats["skipped_existing"] += len(batch_records) - inserted
            batch_records = []
        if batch_errors:
            log_errors(engine, batch_errors)
            batch_errors = []

    # Now it take one line at a time, do some logic and insert into db
    for line_number, raw_line in stream_lines(log_path):
        stats["total_lines"] += 1

        
        if not raw_line.strip():
            stats["malformed"] += 1
            batch_errors.append({"line_number": line_number, "raw_line": raw_line,
                                  "reason": "blank line"})
            continue

        h = record_hash(raw_line)
        if h in seen_hashes:
            stats["duplicate_in_run"] += 1
            continue

        try:
            parsed = parse_line(raw_line)
            record = validate_record(parsed)
        except Exception as e:
            stats["malformed"] += 1
            batch_errors.append({"line_number": line_number, "raw_line": raw_line,
                                  "reason": str(e)[:500]})
            continue

        seen_hashes.add(h)
        stats["valid"] += 1
        batch_records.append({
            "record_hash": h,
            "ip": record.ip,
            "ts": record.timestamp,
            "method": record.method,
            "path": record.path,
            "status": record.status,
            "size": record.size,
        })

        if len(batch_records) >= BATCH_SIZE or len(batch_errors) >= BATCH_SIZE:
            flush()

    flush()  # final partial batch

    logger.info("Run summary: %s", stats)
    return stats


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_access.log"
    run_pipeline(path)
