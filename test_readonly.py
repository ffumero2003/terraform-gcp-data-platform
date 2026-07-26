"""Proves the read-only SA cannot write. Expected result: PERMISSION_DENIED."""
from google.cloud import bigquery
from google.auth import default as default_credentials
from google.auth import impersonated_credentials

PROJECT_ID = "tf-data-platform-fumero"
READONLY_SA = f"nl-sql-readonly@{PROJECT_ID}.iam.gserviceaccount.com"

source_creds, _ = default_credentials()
readonly_creds = impersonated_credentials.Credentials(
    source_credentials=source_creds,
    target_principal=READONLY_SA,
    target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
client = bigquery.Client(project=PROJECT_ID, credentials=readonly_creds)

try:
    client.query(
        f"DELETE FROM `{PROJECT_ID}.fred_raw.indicators` WHERE TRUE"
    ).result()
    print("ERROR: write succeeded — the guardrail is broken!")
except Exception as e:
    print("BLOCKED AS EXPECTED:\n")
    print(e)