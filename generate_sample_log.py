"""
generate_sample_log.py

Generates a synthetic web server access log in Common Log Format (CLF):

    127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326

We deliberately inject bad rows because the whole point of this pipeline is
to prove we can detect and handle them, not just parse clean data:

    - malformed lines (missing fields / garbage text)
    - duplicate lines (same request logged twice)
    - invalid status codes (e.g. "abc" instead of a number)

This mirrors "large plain-text log files" from the job description.
"""

import random
from datetime import datetime, timedelta

PATHS = ["/index.html", "/api/users", "/login", "/products/42", "/checkout",
         "/static/style.css", "/api/orders", "/favicon.ico", "/about"]
METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE"]
STATUSES = [200, 200, 200, 201, 301, 302, 404, 404, 500, 503]


def random_ip():
    return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"


def clf_line(ts, ip, method, path, status, size):
    ts_str = ts.strftime("%d/%b/%Y:%H:%M:%S -0000")
    return f'{ip} - - [{ts_str}] "{method} {path} HTTP/1.1" {status} {size}'


def generate(path="data/sample_access.log", n_good=5000, n_bad=150, n_dupes=80, seed=42):
    random.seed(seed)
    start = datetime(2024, 1, 1, 0, 0, 0)
    lines = []

    # 1. Good, valid lines
    good_lines = []
    for i in range(n_good):
        ts = start + timedelta(seconds=i * random.randint(1, 5))
        line = clf_line(
            ts, random_ip(), random.choice(METHODS), random.choice(PATHS),
            random.choice(STATUSES), random.randint(100, 50000),
        )
        good_lines.append(line)
    lines.extend(good_lines)

    # 2. Malformed lines — missing fields, garbage, truncated
    malformed_examples = [
        "this is not a log line at all",
        "127.0.0.1 - - [BADTIMESTAMP] \"GET /x HTTP/1.1\" 200 123",
        '10.0.0.5 - - [10/Jan/2024:00:00:00 -0000] "GET /missing-status HTTP/1.1"',
        "",  # blank line
        "999.999.999.999 - - [10/Jan/2024:00:00:00 -0000] \"GET /x HTTP/1.1\" abc 456",
        "192.168.1.1 - - [10/Jan/2024:00:00:00 -0000] \"WEIRDMETHODONLY\" 200 100",
    ]
    for _ in range(n_bad):
        lines.append(random.choice(malformed_examples))

    # 3. Exact duplicates of real lines (simulates log shipper retries / re-sends)
    for _ in range(n_dupes):
        lines.append(random.choice(good_lines))

    random.shuffle(lines)

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {len(lines)} lines to {path}")
    print(f"  good: {n_good}, malformed: {n_bad}, duplicates: {n_dupes}")


if __name__ == "__main__":
    generate()
