# GCP project ID. No default -> Terraform forces you to supply it explicitly.
variable "project_id" {
  type        = string
  description = "GCP project where all resources are created"
}

# Region for regional resources (the GCS bucket).
variable "region" {
  type        = string
  description = "GCP region"
  default     = "us-central1"
}

# BigQuery uses a multi-region "location" (US / EU), NOT a region. Separate var on purpose.
variable "bq_location" {
  type        = string
  description = "BigQuery dataset location"
  default     = "US"
}

# Your own gcloud account - needed to grant yourself impersonation rights.
# Get it with: gcloud config get-value account
variable "developer_email" {
  type        = string
  description = "User account allowed to impersonate the read-only SA"
}