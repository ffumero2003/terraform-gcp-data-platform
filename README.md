# Terraform Data Platform + AI Viewer

A minimal analytics platform on Google Cloud where **every resource is provisioned as code** with Terraform, and a Streamlit + AI viewer on top **can read the data but physically cannot write it** — because the infrastructure won't allow it.

> The AI layer can generate any query it wants, but the service account Terraform gave it can only read. The guardrail is enforced at the infrastructure layer (IAM), not by a string check in application code.

![Architecture](./assets/terraform-architecture.png)

---

## What this is

Terraform provisions the entire stack from a single `terraform apply`:

- a **GCS landing bucket**
- two **BigQuery datasets** — `fred_raw` and `fred_analytics` (raw / dbt-target separation)
- an **`indicators` table** with an explicit, code-defined schema
- a **read-only service account** (`nl-sql-readonly`)
- its **IAM roles** — `bigquery.jobUser` + `bigquery.dataViewer`, and nothing else

A one-time Python loader pulls live FRED economic indicators into BigQuery **as the project owner** (which can write). A Streamlit app on top authenticates **as the read-only service account via impersonation** — no key file ever touches disk — and offers:

- a chart of any indicator, with an "Explain with AI" button that sends the on-screen rows to the model for a plain-English trend read
- an "Ask the data" box that turns a natural-language question into SQL

### The flow

```
question -> the model generates SQL -> shown on screen -> executed as nl-sql-readonly -> IAM rejects writes with a 403
```

1. You type a question in "Ask the data".
2. The model (`gpt-4o-mini`) is given the table schema and returns one BigQuery SQL statement.
3. The SQL is displayed **before** it runs.
4. It is executed through the same impersonated read-only client as everything else in the app.
5. A read returns rows. A write (`INSERT` / `UPDATE` / `DELETE` / `DROP`) is rejected by IAM, and the app shows the 403 message from BigQuery.

<!-- screenshot: nl-sql-denied.png -->

### Why no SQL filter in Python

The app does not check the generated SQL for `DELETE`, `DROP`, or a leading `SELECT`, and the prompt does not tell the model to refuse writes. This is deliberate. A string check is one bug away from failing: a comment trick, an unusual statement form, a refactor that skips the check. An IAM binding has no code path to skip. The service account was never granted a write role, so there is nothing for a bug in the app, or a clever prompt, to bypass.

---

## Why it's built this way

| Decision                           | Reason                                                                                                                  |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 100% Infrastructure-as-Code        | Reproducible, versioned, reviewable. Rebuild the whole platform from one command; every change is a git diff.           |
| Least-privilege service account    | `jobUser` (start a query job) + `dataViewer` (read one dataset) only. No `dataEditor`, no `dataOwner`.                  |
| Impersonation instead of key files | The app borrows the SA's identity at runtime with a short-lived token — no long-lived secret on disk to leak or commit. |
| Separate write vs. read identities | The loader writes as the owner; the app reads as the SA. The two paths are deliberately distinct.                       |
| Guardrail in IAM, not app code     | A write is blocked by the platform, not by a `if query.startswith("SELECT")` check that a bug could bypass.             |

---

## Screenshots

|                                                                       |                                         |
| --------------------------------------------------------------------- | --------------------------------------- |
| **Everything as code** — `terraform state list` shows all 8 resources | ![state](./assets/terraform-state.png)  |
| **The app** — Streamlit viewer, querying as the read-only SA          | ![app](./assets/streamlit-app.png)      |
| **The guardrail** — a write attempt is rejected by IAM                | ![denied](./assets/readonly-denied.png) |

---

## Stack

Terraform (GCP provider) · Google Cloud (BigQuery, GCS, IAM) · Python · pandas · Streamlit · FRED API · OpenAI API

---

## Running it locally

### Prerequisites

- Terraform >= 1.5
- `gcloud` CLI, authenticated (`gcloud auth application-default login`)
- A GCP project with billing enabled
- A [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) and an [OpenAI API key](https://platform.openai.com/api-keys)

### 1. Configure

Create `terraform.tfvars`:

```hcl
project_id      = "your-gcp-project-id"
developer_email = "your-gcloud-account@example.com"
```

Create `.env` (gitignored) from the template:

```bash
cp .env.example .env   # then fill in FRED_API_KEY and OPENAI_API_KEY
```

### 2. Provision the infrastructure

```bash
terraform init
terraform plan      # dry run — review what will be created
terraform apply     # creates all resources
```

### 3. Load data and run the app

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python load_data.py     # loads FRED indicators (runs as owner)
streamlit run app.py    # opens the viewer at localhost:8501
```

### 4. Prove the guardrail

```bash
python test_readonly.py
```

It runs two tests as the SA: a hand-written `DELETE ... WHERE TRUE`, and a question sent through `generate_sql()` asking the model to delete all rows. Each is expected to be rejected with a 403, and the raw error message is printed. The second test is skipped if the model does not produce a `DELETE`.

<!-- screenshot: nl-sql-test-output.png -->

### 5. Tear it all down

```bash
terraform destroy     # removes every resource this repo created
```

---

## Repo layout

```
.
├── main.tf              # provider + all resources (bucket, datasets, table, SA, IAM)
├── variables.tf         # inputs (project_id, region, bq_location, developer_email)
├── outputs.tf           # bucket name, dataset, table path, SA email
├── load_data.py         # one-time FRED -> BigQuery loader (runs as owner)
├── app.py               # Streamlit viewer (runs as read-only SA via impersonation)
├── nl_sql.py            # model SQL generation + query helper (no Streamlit, importable by tests)
├── test_readonly.py     # proves the SA cannot write (hand-written and model-generated DELETE)
├── requirements.txt     # Python dependencies
├── .env.example         # template for .env
├── claude-plans/        # planning notes
├── assets/              # README images (architecture diagram, screenshots)
└── .gitignore           # ignores state, .env, tfvars, venv
```

## Notes / scope

Deliberately minimal — one bucket, two datasets, one table, one service account, a one-page viewer, an "Explain with AI" button, and an "Ask the data" box. The point is the **infrastructure-enforced read-only boundary**, not feature breadth. State is local (no remote backend), metadata is not persisted beyond BigQuery, and resources are torn down with `terraform destroy` after use.
