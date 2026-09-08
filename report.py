"""
report.py

Reads the processed data back OUT of Postgres and produces the kind of
output a dashboard or a stakeholder actually wants: summary stats, not
raw rows. This is the "reporting" stage of the JD's pipeline
(raw ingestion -> validation -> processing -> storage -> REPORTING/API).

We use pandas here for what it's actually good at: groupby aggregations
that would be verbose to write as separate SQL queries and then stitch
together by hand.
"""

import pandas as pd
from sqlalchemy import create_engine

DB_URL = "postgresql+psycopg2://dbuser:dbpassword@db:5432/logdatabase"


def load_data(engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM access_log", engine)


def load_errors(engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM ingestion_errors", engine)


def build_summary(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Returns a dict of {sheet_name: DataFrame} -- each becomes one
    tab in the Excel report and one CSV file."""

    requests_per_hour = (
        # Excel has no concept of timezone-aware datetimes, so we drop the
        # tz info here (tz_localize(None)) purely for report output --
        # the underlying Postgres data keeps full tz-aware timestamps.
        df.assign(hour=df["ts"].dt.floor("h").dt.tz_localize(None))
        .groupby("hour")
        .size()
        .reset_index(name="request_count")
        .sort_values("hour")
    )

    status_breakdown = (
        df.groupby("status")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    top_paths = (
        df.groupby("path")
        .size()
        .reset_index(name="hits")
        .sort_values("hits", ascending=False)
        .head(10)
    )

    top_ips = (
        df.groupby("ip")
        .size()
        .reset_index(name="requests")
        .sort_values("requests", ascending=False)
        .head(10)
    )

    error_rate_by_status_class = df.assign(
        status_class=df["status"].astype(str).str[0] + "xx"
    ).groupby("status_class").size().reset_index(name="count")

    return {
        "requests_per_hour": requests_per_hour,
        "status_breakdown": status_breakdown,
        "top_paths": top_paths,
        "top_ips": top_ips,
        "status_class_breakdown": error_rate_by_status_class,
    }


def write_reports(summary: dict[str, pd.DataFrame], out_dir: str = "reports"):
    # One combined Excel workbook, one sheet per summary table
    excel_path = f"{out_dir}/log_report.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for sheet_name, sheet_df in summary.items():
            sheet_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    print(f"Wrote {excel_path}")

    # Separate CSVs too, since some tooling / stakeholders prefer plain CSV
    for name, sheet_df in summary.items():
        csv_path = f"{out_dir}/{name}.csv"
        sheet_df.to_csv(csv_path, index=False)
        print(f"Wrote {csv_path}")


if __name__ == "__main__":
    engine = create_engine(DB_URL)
    df = load_data(engine)
    print(f"Loaded {len(df)} processed records from Postgres")

    summary = build_summary(df)
    write_reports(summary)

    errors_df = load_errors(engine)
    errors_df.to_csv("reports/ingestion_errors.csv", index=False)
    print(f"Wrote reports/ingestion_errors.csv ({len(errors_df)} error rows)")
