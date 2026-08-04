# --- GitHub Actions CI/CD Service Account & OIDC Workload Identity Pool ---

resource "google_service_account" "github_ci" {
  account_id   = "mvcp-github-ci-sa"
  display_name = "MVCP GitHub Actions CI/CD Deployment Runner"
  description  = "Service account used by GitHub Actions workflows for automated build, push, and deployment"
}

resource "google_project_iam_member" "github_ci_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_ci.email}"
}

resource "google_project_iam_member" "github_ci_gke_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_ci.email}"
}

resource "google_iam_workload_identity_pool" "github_actions_pool" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "OIDC identity pool for GitHub Actions CI/CD workflows"
  disabled                  = false
}

resource "google_iam_workload_identity_pool_provider" "github_actions_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions Provider"
  attribute_condition                = "attribute.repository in ['${var.control_plane_repository}', '${var.workspace_repository}']"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_ci_workload_identity" {
  service_account_id = google_service_account.github_ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions_pool.name}/attribute.repository/${var.control_plane_repository}"
}

resource "google_service_account_iam_member" "github_ci_workload_identity_workspace" {
  service_account_id = google_service_account.github_ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions_pool.name}/attribute.repository/${var.workspace_repository}"
}

# --- Control Plane Gateway Service Account & Workload Identity Binding ---

resource "google_service_account" "mvcp_gateway" {
  account_id   = "mvcp-gateway-gsa"
  display_name = "MVCP Control Plane Gateway Workload Identity"
  description  = "Service account bound to the in-cluster mvcp-gateway Kubernetes ServiceAccount"
}

resource "google_service_account_iam_member" "mvcp_gateway_workload_identity" {
  service_account_id = google_service_account.mvcp_gateway.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/mvcp-gateway-sa]"
}

resource "google_project_iam_member" "mvcp_gateway_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.mvcp_gateway.email}"
}
