# Log Processing Pipeline

pipeline: **raw log ingestion - parsing - validation - processing - storage - reporting**

Built to close a specific gap: proving hands-on experience with log/data
parsing, batch processing, and idempotent data pipelines — on top of an
existing Django/DRF/Celery/PostgreSQL background.

## Architecture

```
sample_access.log
      │
      ▼
stream_lines()          generator — reads one line at a time, constant memory
      │
      ▼
parse_line()             regex → structured dict (parser.py)
      │
      ▼
validate_record()        Pydantic → typed, validated LogRecord (validator.py)
      │
      ▼
dedupe (SHA-256 hash)     skips exact repeats within the same run
      │
      ▼
batch into DataFrame      every 500 valid records (via pandas)
      │
      ▼
INSERT ... ON CONFLICT    idempotent upsert into Postgres (pipeline.py)
      │
      ▼
report.py                 CSV + Excel summary reports
```

Malformed / invalid lines never crash the run — they're caught, logged
with a line number and insert in `ingestion_errors` table,
and processing continues.

## Why it's idempotent

Every row's primary key is a SHA-256 hash of its raw log line. The insert
uses `ON CONFLICT (record_hash) DO NOTHING`. Re-running the pipeline on
the same file (e.g. after a crash, or a log shipper re-sending a batch)
inserts zero duplicate rows.

## Setup

```bash
pip install -r requirements.txt

# Requires a running Postgres. Update DB_URL in pipeline.py and in report.py
# if your connection details differ from the default
# db_url = dbuser/dbpassword@db:5432/logdatabase 

```

## Run it

```bash
# 1. Buid the image and spin up the container
docker compose up --build -d

# 1. Generate a synthetic log file (5000 valid rows, 150 malformed, 80 duplicates)
docker compose exec app python generate_sample_log.py

# 2. Run the pipeline (safe to re-run any number of times)
docker compose exec app python pipeline.py data/sample_access.log

# 3. Generate reports from what's now in Postgres
docker compose exec app python report.py

# 4. Run the test suite
docker compose exec app python -m pytest tests/ -v
```
