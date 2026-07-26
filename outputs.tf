# Printed after apply; also readable anytime via `terraform output`.

output "landing_bucket" {
  value       = google_storage_bucket.landing.name
  description = "GCS landing bucket"
}

output "raw_dataset" {
  value       = google_bigquery_dataset.raw.dataset_id
  description = "Raw BigQuery dataset"
}

output "indicators_table" {
  # Fully-qualified name you can paste straight into a query.
  value       = "${var.project_id}.${google_bigquery_dataset.raw.dataset_id}.${google_bigquery_table.indicators.table_id}"
  description = "Full path to the indicators table"
}

output "readonly_sa_email" {
  value       = google_service_account.nl_sql_readonly.email
  description = "Service account the app authenticates as"
}