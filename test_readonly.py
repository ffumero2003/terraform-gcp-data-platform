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


def check_iam_denial(err: Forbidden, expected_permission: str) -> str:
    """
    Print the raw reason and message of a Forbidden, then decide if it is the RIGHT
    403: an IAM accessDenied naming the expected missing permission. Returns "passed"
    or "failed". Change this if BigQuery's error shape or the expected roles change.
    """
    # Real Forbidden objects here carry errors=[{"reason", "message"}]; the
    # permission name only appears inside the message text.
    first = err.errors[0] if err.errors else {}
    reason = first.get("reason")
    message = first.get("message") or err.message
    print(f"Raw reason:  {reason}")
    print(f"Raw message: {message}\n")

    if reason == "billingNotEnabled":
        print("FAILED: billingNotEnabled - the project is in sandbox mode, so this 403 is "
              "not from IAM and proves nothing about the read-only SA. Enable billing.")
        return "failed"
    if reason != "accessDenied":
        print(f"FAILED: expected reason accessDenied, got {reason!r}.")
        return "failed"
    if "bigquery.jobs.create" in message:
        print("FAILED: jobUser binding missing, SA can't start queries at all.")
        return "failed"
    if expected_permission not in message:
        print(f"FAILED: accessDenied, but the message does not name {expected_permission}.")
        return "failed"
    print(f"BLOCKED BY IAM AS EXPECTED: accessDenied naming {expected_permission}.")
    return "passed"


def test_handwritten_delete(client: bigquery.Client) -> str:
    """
    Run a hand-written DELETE as the SA and expect an IAM accessDenied 403.
    Returns "passed" or "failed"; change the SQL here to probe other writes.
    """
    print("TEST RAN: handwritten DELETE ... WHERE TRUE")
    try:
        client.query(
            f"DELETE FROM `{PROJECT_ID}.fred_raw.indicators` WHERE TRUE"
        ).result()
    except Forbidden as e:
        return check_iam_denial(e, "bigquery.tables.updateData")
    except Exception as e:
        print(f"FAILED: expected Forbidden, got {type(e).__name__}:\n")
        print(e)
        return "failed"
    print("ERROR: write succeeded - the guardrail is broken!")
    return "failed"


def test_handwritten_drop(client: bigquery.Client) -> str:
    """
    Run a hand-written DROP TABLE as the SA and expect an IAM accessDenied 403
    naming bigquery.tables.delete. Returns "passed" or "failed"; unlike DML, DDL is
    not blocked by the free-tier billing rule, so this shows IAM even in sandbox mode.
    """
    print("TEST RAN: handwritten DROP TABLE")
    try:
        client.query(f"DROP TABLE `{PROJECT_ID}.fred_raw.indicators`").result()
    except Forbidden as e:
        return check_iam_denial(e, "bigquery.tables.delete")
    except Exception as e:
        print(f"FAILED: expected Forbidden, got {type(e).__name__}:\n")
        print(e)
        return "failed"
    print("ERROR: DROP succeeded - the guardrail is broken!")
    return "failed"


def test_generated_delete(client: bigquery.Client) -> str:
    """
    Ask the model for a delete-everything statement, run it as the SA, expect an IAM accessDenied 403.
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
        return check_iam_denial(e, "bigquery.tables.updateData")
    except Exception as e:
        print(f"FAILED: expected Forbidden, got {type(e).__name__}:\n")
        print(e)
        return "failed"
    print("ERROR: generated write succeeded - the guardrail is broken!")
    return "failed"


def main() -> int:
    """Run all tests, print a summary, and return a nonzero exit code on any failure."""
    client = build_readonly_client()
    results = {
        "handwritten_delete": test_handwritten_delete(client),
    }
    print()
    results["handwritten_drop"] = test_handwritten_drop(client)
    print()
    results["generated_delete"] = test_generated_delete(client)
    print(f"\nSummary: {results}")
    return 1 if "failed" in results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
