# ==============================================================================
# LEAST-PRIVILEGE IAM & SERVICE ACCOUNT CONFIGURATION
# ==============================================================================

# --- Default Compute Service Account (Used by existing GKE cluster) ---
data "google_compute_default_service_account" "default" {
  project = var.project_id
}

resource "google_project_iam_member" "gke_default_nodes_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

# --- 1. Dedicated GKE Worker Node Service Account ---
resource "google_service_account" "gke_nodes" {
  account_id   = "mvcp-gke-nodes-sa"
  display_name = "MVCP GKE Worker Nodes Service Account"
  description  = "Dedicated least-privilege service account assigned to GKE node pool"
}

# IAM Role: Artifact Registry Reader (Allows pulling images seamlessly without ImagePullBackOff)
resource "google_project_iam_member" "gke_nodes_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# IAM Role: Cloud Logging Writer
resource "google_project_iam_member" "gke_nodes_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# IAM Role: Cloud Monitoring Metric Writer
resource "google_project_iam_member" "gke_nodes_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# IAM Role: Stackdriver Resource Metadata Writer
resource "google_project_iam_member" "gke_nodes_metadata" {
  project = var.project_id
  role    = "roles/stackdriver.resourceMetadata.writer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# --- 2. GitHub Actions CI/CD Deployment Service Account ---
resource "google_service_account" "github_ci" {
  account_id   = "mvcp-github-ci-sa"
  display_name = "MVCP GitHub Actions CI/CD Deployment Runner"
  description  = "Service account used by GitHub Actions workflows for automated build, push, and deployment"
}

# IAM Role: Artifact Registry Writer (Allows pushing container images)
resource "google_project_iam_member" "github_ci_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_ci.email}"
}

# IAM Role: GKE Developer (Allows kubectl apply, set image, rollout status)
resource "google_project_iam_member" "github_ci_gke_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_ci.email}"
}

# Bind GitHub Actions OIDC Workload Identity Pool to mvcp-github-ci-sa
resource "google_service_account_iam_member" "github_ci_workload_identity" {
  service_account_id = google_service_account.github_ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/389363417412/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/markdavidmc0/arm-ai-control-plane"
}

# --- 3. Workload Identity Service Account for Control Plane Gateway ---
resource "google_service_account" "mvcp_gateway" {
  account_id   = "mvcp-gateway-gsa"
  display_name = "MVCP Control Plane Gateway Workload Identity"
  description  = "Service account bound to the in-cluster mvcp-gateway Kubernetes ServiceAccount"
}

# Bind GKE Workload Identity (KSA -> GSA)
resource "google_service_account_iam_member" "mvcp_gateway_workload_identity" {
  service_account_id = google_service_account.mvcp_gateway.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/mvcp-gateway-sa]"

  depends_on = [
    google_container_cluster.primary
  ]
}
