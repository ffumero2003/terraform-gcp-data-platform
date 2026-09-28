"""
Natural-language-to-SQL helpers, kept free of Streamlit so tests can import them.

The model generates SQL and this code runs it as the read-only service account.
There is deliberately NO SQL filtering here: IAM is the only guardrail.
"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

import pandas as pd
from openai import OpenAI
from google.cloud import bigquery

PROJECT_ID = "tf-data-platform-fumero"
TABLE_ID = f"{PROJECT_ID}.fred_raw.indicators"

# Schema copied from google_bigquery_table.indicators in main.tf. If that
# schema changes, update this string to match.
SCHEMA_DESCRIPTION = """\
Table: `{table}`
Columns:
  series_id    STRING     NULLABLE
  indicator    STRING     NULLABLE
  date         DATE       NULLABLE
  value        FLOAT      NULLABLE
  ingested_at  TIMESTAMP  NULLABLE
""".format(table=TABLE_ID)

# DELIBERATE: this prompt does not tell the model to refuse writes, and no Python
# code in this project blocks DELETE/UPDATE/INSERT/DROP or requires SELECT.
# The read-only service account's IAM roles are the only guardrail, on purpose.
SYSTEM_PROMPT = (
    "You translate a user's question into a single BigQuery Standard SQL statement.\n\n"
    f"{SCHEMA_DESCRIPTION}\n"
    "Reply with ONLY the SQL statement. No markdown code fences, no explanation, "
    "no prose."
)


def strip_fences(text: str) -> str:
    """
    Remove markdown code fences the model may add despite instructions.
    Change this if the model starts wrapping output in some other format.
    """
    text = text.strip()
    match = re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```$", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def generate_sql(question: str) -> str:
    """
    Ask the model to turn a natural-language question into one BigQuery SQL statement.
    Change this to alter the model, the prompt, or the schema the model sees.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )
    return strip_fences(response.choices[0].message.content)


def execute_sql(client: bigquery.Client, sql: str) -> pd.DataFrame:
    """
    Run a SQL string on the given client and return the rows as a DataFrame.
    This is the one place generated SQL reaches BigQuery; change it if result
    handling changes. Permission errors are raised, not caught, here.
    """
    return client.query(sql).to_dataframe()
