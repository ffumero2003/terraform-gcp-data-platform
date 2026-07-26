"""
One-time loader: FRED indicators -> BigQuery fred_raw.indicators

Runs with YOUR credentials (gcloud ADC / owner), NOT the read-only service account.
That separation is deliberate: loading requires write permission, and the app's
service account does not have it.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env into os.environ so FRED_API_KEY loads automatically
from datetime import datetime, timezone

import pandas as pd
import requests
from google.cloud import bigquery

# --- config ---------------------------------------------------------------
PROJECT_ID = "tf-data-platform-fumero"
TABLE_ID = f"{PROJECT_ID}.fred_raw.indicators"

# Set with: export FRED_API_KEY="your_key"
FRED_API_KEY = os.environ["FRED_API_KEY"]

# series_id -> human-readable name stored alongside it
SERIES = {
    "CPIAUCSL": "US CPI (All Urban Consumers)",
    "UNRATE": "US Unemployment Rate",
    "FEDFUNDS": "Federal Funds Effective Rate",
    "GDPC1": "US Real GDP",
    "DEXMXUS": "Mexican Peso / USD Exchange Rate",
}

START_DATE = "2015-01-01"


def fetch_series(series_id: str, name: str) -> pd.DataFrame:
    """Pull one FRED series and shape it to match the Terraform-defined schema."""
    resp = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "observation_start": START_DATE,
        },
        timeout=30,
    )
    resp.raise_for_status()

    df = pd.DataFrame(resp.json()["observations"])

    # FRED marks missing values as "." - coerce turns those into NaN.
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # Column names/types must match the schema Terraform created, or the load fails.
    return pd.DataFrame({
        "series_id": series_id,
        "indicator": name,
        "date": pd.to_datetime(df["date"]).dt.date,
        "value": df["value"].astype(float),
        "ingested_at": datetime.now(timezone.utc),
    })


def main() -> None:
    frames = []
    for series_id, name in SERIES.items():
        print(f"Fetching {series_id}...")
        frames.append(fetch_series(series_id, name))

    data = pd.concat(frames, ignore_index=True)
    print(f"Total rows: {len(data)}")

    client = bigquery.Client(project=PROJECT_ID)

    job_config = bigquery.LoadJobConfig(
        # Replace the table contents each run -> the script is idempotent.
        # Run it twice, you get the same result, not duplicated rows.
        write_disposition="WRITE_TRUNCATE",
        # Do NOT let BigQuery guess the schema; Terraform already defined it.
        autodetect=False,
    )

    job = client.load_table_from_dataframe(data, TABLE_ID, job_config=job_config)
    job.result()  # blocks until the load finishes

    print(f"Loaded {client.get_table(TABLE_ID).num_rows} rows into {TABLE_ID}")


if __name__ == "__main__":
    main()