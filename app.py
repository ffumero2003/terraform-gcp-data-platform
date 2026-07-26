"""
Streamlit viewer over the Terraform-provisioned BigQuery table.

Key point: this app authenticates as nl-sql-readonly. Every query it runs -
including anything the model generates - is executed by an identity that has
dataViewer + jobUser and nothing else. Writes fail at the IAM layer, not in
application code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

import pandas as pd
import streamlit as st
from openai import OpenAI
from google.cloud import bigquery
from google.auth import default as default_credentials
from google.auth import impersonated_credentials

PROJECT_ID = "tf-data-platform-fumero"
TABLE_ID = f"{PROJECT_ID}.fred_raw.indicators"
READONLY_SA = f"nl-sql-readonly@{PROJECT_ID}.iam.gserviceaccount.com"


@st.cache_resource
def get_client() -> bigquery.Client:
    """
    Build a BigQuery client that acts as the read-only service account.

    Flow: your ADC credentials -> impersonate the SA -> short-lived token.
    Nothing is written to disk, and the resulting client inherits ONLY the
    SA's permissions, not yours.
    """
    source_creds, _ = default_credentials()

    readonly_creds = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal=READONLY_SA,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=3600,
    )
    return bigquery.Client(project=PROJECT_ID, credentials=readonly_creds)


@st.cache_data(ttl=600)
def load_indicator(series_id: str) -> pd.DataFrame:
    """Read one indicator's time series. Parameterized query - no SQL injection."""
    query = f"""
        SELECT date, value, indicator
        FROM `{TABLE_ID}`
        WHERE series_id = @series_id
        ORDER BY date
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("series_id", "STRING", series_id)
        ]
    )
    return get_client().query(query, job_config=config).to_dataframe()


@st.cache_data(ttl=600)
def list_indicators() -> pd.DataFrame:
    """Populate the dropdown from what's actually in the table."""
    query = f"SELECT DISTINCT series_id, indicator FROM `{TABLE_ID}` ORDER BY indicator"
    return get_client().query(query).to_dataframe()


def explain_with_ai(df: pd.DataFrame, indicator_name: str) -> str:
    """Send the on-screen rows to the model for a plain-English read of the trend."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Only the visible data goes to the model - it gets no DB access of its own.
    sample = df.tail(40).to_csv(index=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # cheap, same one you used in PuffZero
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": "You are a data analyst who explains trends to non-technical business readers.",
            },
            {
                "role": "user",
                "content": (
                    f"Below is recent data for '{indicator_name}'.\n\n"
                    f"{sample}\n\n"
                    "In 3-4 short paragraphs, explain the trend in plain English. "
                    "Mention direction, notable inflection points, and what it might "
                    "indicate. Do not invent data not shown."
                ),
            },
        ],
    )
    return response.choices[0].message.content


# --- UI -------------------------------------------------------------------
st.set_page_config(page_title="FRED Indicators", layout="wide")
st.title("FRED Economic Indicators")
st.caption(f"Infrastructure provisioned by Terraform · querying as `{READONLY_SA}`")

indicators = list_indicators()
choice = st.selectbox(
    "Indicator",
    options=indicators["series_id"],
    format_func=lambda sid: indicators.set_index("series_id").loc[sid, "indicator"],
)

data = load_indicator(choice)
name = data["indicator"].iloc[0]

st.line_chart(data.set_index("date")["value"])

col_a, col_b = st.columns([1, 2])
with col_a:
    st.metric("Rows", len(data))
    st.metric("Latest", f"{data['value'].iloc[-1]:,.2f}")
with col_b:
    st.dataframe(data.tail(10), use_container_width=True)

if st.button("Explain with AI", type="primary"):
    with st.spinner("Analyzing..."):
        st.markdown(explain_with_ai(data, name))

with st.expander("Why this app cannot write to BigQuery"):
    st.markdown(
        f"""
        The app impersonates `{READONLY_SA}`, which Terraform granted exactly two roles:

        - `roles/bigquery.jobUser` (project) — permission to *start* a query job
        - `roles/bigquery.dataViewer` (scoped to `fred_raw` only) — permission to *read*

        No `dataEditor`, no `dataOwner`. An INSERT, UPDATE, or DELETE is rejected by
        IAM before it reaches the data. The guardrail is infrastructure, not a
        string check in Python.
        """
    )