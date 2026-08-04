# --- VPC & Networking Setup ---

resource "google_compute_network" "vpc_network" {
  name                    = "mvcp-vpc-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name                     = "mvcp-subnetwork"
  ip_cidr_range            = "10.0.0.0/20"
  region                   = var.region
  network                  = google_compute_network.vpc_network.id
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "mvcp-pods"
    ip_cidr_range = var.pods_cidr_range
  }

  secondary_ip_range {
    range_name    = "mvcp-services"
    ip_cidr_range = var.services_cidr_range
  }
}

# --- Firewall Rules ---

resource "google_compute_firewall" "allow_envoy" {
  name    = "mvcp-allow-envoy"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["10000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["gke-node"]
}

# --- GKE Cluster Base ---

resource "google_container_cluster" "primary" {
  provider = google-beta
  name     = var.cluster_name
  location = var.zone

  network    = google_compute_network.vpc_network.self_link
  subnetwork = google_compute_subnetwork.subnet.self_link

  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "mvcp-pods"
    services_secondary_range_name = "mvcp-services"
  }

  release_channel {
    channel = "REGULAR"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }

  lifecycle {
    ignore_changes = [
      initial_node_count,
    ]
  }
}

# --- Cloud DNS Private Managed Zone for arm.internal ---

resource "google_dns_managed_zone" "arm_internal" {
  name        = "arm-internal-zone"
  dns_name    = "arm.internal."
  description = "Private DNS zone for internal platform service discovery"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = google_compute_network.vpc_network.id
    }
  }
}

# --- GCP Artifact Registry for MCP Tools Container Images ---

resource "google_artifact_registry_repository" "mcp_tools" {
  location      = var.region
  repository_id = "mcp-tools"
  description   = "GCP Artifact Registry Docker repository for Arm Workspace Multi-Language Tools OCI images"
  format        = "DOCKER"
}
