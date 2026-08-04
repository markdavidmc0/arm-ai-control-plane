# --- Dedicated GKE Worker Node Service Account ---

resource "google_service_account" "gke_nodes" {
  account_id   = "mvcp-gke-nodes-sa"
  display_name = "MVCP GKE Worker Nodes Service Account"
  description  = "Dedicated least-privilege service account assigned to GKE node pools"
}

resource "google_project_iam_member" "gke_nodes_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# --- Dynamic GKE Node Pools Map (gVisor Sandboxed & Native Baseline) ---

resource "google_container_node_pool" "pools" {
  provider = google-beta
  for_each = var.node_pools

  name       = "arm-${each.key}-pool"
  location   = var.zone
  cluster    = var.cluster_name
  node_count = each.value.node_count

  node_config {
    machine_type    = each.value.machine_type
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.gke_nodes.email

    dynamic "sandbox_config" {
      for_each = each.value.is_gvisor ? [1] : []
      content {
        sandbox_type = "gvisor"
      }
    }

    dynamic "taint" {
      for_each = each.value.taints
      content {
        key    = taint.value.key
        value  = taint.value.value
        effect = taint.value.effect
      }
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    labels = each.value.labels
    tags   = ["gke-node"]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
