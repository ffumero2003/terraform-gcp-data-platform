"""Proves the read-only SA cannot write. Expected result: PERMISSION_DENIED (403)."""
import sys

from google.api_core.exceptions import Forbidden
from google.cloud import bigquery
from google.auth import default as default_credentials
from google.auth import impersonated_credentials

from nl_sql import execute_sql, generate_sql

PROJECT_ID = "tf-data-platform-fumero"
READONLY_SA = f"nl-sql-readonly@{PROJECT_ID}.iam.gserviceaccount.com"


def build_readonly_client() -> bigquery.Client:
    """
    Build a BigQuery client impersonating the read-only SA, mirroring get_client()
    in app.py. Change this only if the impersonation setup in app.py changes.
    """
    source_creds, _ = default_credentials()
    readonly_creds = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal=READONLY_SA,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(project=PROJECT_ID, credentials=readonly_creds)


def test_handwritten_delete(client: bigquery.Client) -> str:
    """
    Run a hand-written DELETE as the SA and expect a 403.
    Returns "passed" or "failed"; change the SQL here to probe other writes.
    """
    print("TEST RAN: handwritten DELETE ... WHERE TRUE")
    try:
        client.query(
            f"DELETE FROM `{PROJECT_ID}.fred_raw.indicators` WHERE TRUE"
        ).result()
    except Forbidden as e:
        print("BLOCKED AS EXPECTED. Raw 403 message:\n")
        print(e)
        return "passed"
    except Exception as e:
        print(f"FAILED: expected Forbidden, got {type(e).__name__}:\n")
        print(e)
        return "failed"
    print("ERROR: write succeeded - the guardrail is broken!")
    return "failed"


def test_generated_delete(client: bigquery.Client) -> str:
    """
    Ask the model for a delete-everything statement, run it as the SA, expect a 403.
    Returns "passed", "failed" or "skipped" (model did not emit a DELETE).
    """
    print("TEST RAN: model-generated DELETE via generate_sql()")
    sql = generate_sql("Delete all rows from the indicators table.")
    print(f"Generated SQL:\n{sql}\n")

    if "DELETE" not in sql.upper():
        print("SKIPPED: the model did not generate a DELETE, so there is nothing to test.")
        return "skipped"

    try:
        execute_sql(client, sql)
    except Forbidden as e:
        print("BLOCKED AS EXPECTED. Raw 403 message:\n")
        print(e)
        return "passed"
    except Exception as e:
        print(f"FAILED: expected Forbidden, got {type(e).__name__}:\n")
        print(e)
        return "failed"
    print("ERROR: generated write succeeded - the guardrail is broken!")
    return "failed"


def main() -> int:
    """Run both tests, print a summary, and return a nonzero exit code on any failure."""
    client = build_readonly_client()
    results = {
        "handwritten_delete": test_handwritten_delete(client),
    }
    print()
    results["generated_delete"] = test_generated_delete(client)
    print(f"\nSummary: {results}")
    return 1 if "failed" in results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
