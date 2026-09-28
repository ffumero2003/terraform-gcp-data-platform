terraform {
  required_version = ">= 1.5"

  # Pins the provider plugin so a future major release can't silently break this repo.
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.41"
    }
  }
}

# Configures the google provider. Credentials come from
# `gcloud auth application-default login` (ADC) - never hardcoded.
provider "google" {
  project = var.project_id
  region  = var.region
}


# ---------------------------------------------------------------------------
# LANDING BUCKET - where raw files land before loading into BigQuery
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "landing" {
  # Bucket names are globally unique across ALL of GCP, so prefix with project id.
  name     = "${var.project_id}-landing"
  location = var.region

  # Lets `terraform destroy` delete the bucket even if files are inside.
  # Fine for a demo; you would NOT set this in production.
  force_destroy = true

  # Permissions come only from IAM, not legacy per-object ACLs.
  uniform_bucket_level_access = true
}

# ---------------------------------------------------------------------------
# BIGQUERY DATASETS - raw vs analytics separation (dbt-target pattern)
# ---------------------------------------------------------------------------
resource "google_bigquery_dataset" "raw" {
  dataset_id  = "fred_raw"
  location    = var.bq_location # "US" - a multi-region, not a region
  description = "Raw FRED indicator data as ingested"

  # Allows destroy to drop the dataset even when it still contains tables.
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "analytics" {
  dataset_id  = "fred_analytics"
  location    = var.bq_location
  description = "Modeled/analytics-ready layer (dbt target)"

  delete_contents_on_destroy = true
}

# ---------------------------------------------------------------------------
# TABLE - explicit schema, defined as code (contract safety)
# ---------------------------------------------------------------------------
resource "google_bigquery_table" "indicators" {
  dataset_id = google_bigquery_dataset.raw.dataset_id # implicit dependency: dataset built first
  table_id   = "indicators"

  # Without this, destroy refuses to delete a table that holds data.
  deletion_protection = false

  # Schema is JSON. jsonencode() lets you write native HCL instead of a raw string.
  schema = jsonencode([
    { name = "series_id", type = "STRING", mode = "NULLABLE" },
    { name = "indicator", type = "STRING", mode = "NULLABLE" },
    { name = "date", type = "DATE", mode = "NULLABLE" },
    { name = "value", type = "FLOAT", mode = "NULLABLE" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "NULLABLE" }
  ])
}

# ---------------------------------------------------------------------------
# READ-ONLY SERVICE ACCOUNT - the core of the story.
# The Streamlit app runs AS this identity, including the SQL that the model
# generates from natural-language questions. It has no write role, so writes
# are rejected by IAM, not by application code.
# ---------------------------------------------------------------------------
resource "google_service_account" "nl_sql_readonly" {
  account_id   = "nl-sql-readonly"
  display_name = "Read-only SA for the NL-to-SQL app"
  description  = "Can run queries and read data. No write, update, or delete permission."
}

# jobUser is PROJECT-level: without it the SA cannot start a query job at all,
# even on data it is allowed to read. This is the role people forget.
resource "google_project_iam_member" "sa_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.nl_sql_readonly.email}"
}

# dataViewer is scoped to the DATASET, not the project - least privilege.
# The SA can read fred_raw and nothing else in the project.
resource "google_bigquery_dataset_iam_member" "sa_raw_viewer" {
  dataset_id = google_bigquery_dataset.raw.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.nl_sql_readonly.email}"
}

# ---------------------------------------------------------------------------
# IMPERSONATION - lets the developer run the app AS the read-only SA
# without ever downloading a key file. No long-lived secret on disk.
# ---------------------------------------------------------------------------
resource "google_service_account_iam_member" "developer_can_impersonate" {
  service_account_id = google_service_account.nl_sql_readonly.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.developer_email}"
}

