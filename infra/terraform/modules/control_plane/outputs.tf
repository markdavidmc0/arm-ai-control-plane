output "gateway_service_account_email" {
  value       = google_service_account.mvcp_gateway.email
  description = "The email address of the Control Plane Gateway Workload Identity service account."
}

output "github_ci_service_account_email" {
  value       = google_service_account.github_ci.email
  description = "The email address of the GitHub Actions CI/CD deployment service account."
}

output "workload_identity_provider_id" {
  value       = google_iam_workload_identity_pool_provider.github_actions_provider.name
  description = "The full resource name of the GitHub Actions Workload Identity Provider."
}
