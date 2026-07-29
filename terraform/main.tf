terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

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
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "mvcp-services"
    ip_cidr_range = "10.8.0.0/20"
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

resource "google_compute_firewall" "allow_tailscale" {
  name    = "mvcp-allow-tailscale"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "udp"
    ports    = ["41641"]
  }

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["gke-node"]
}

# --- GKE Cluster ---

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

# --- Arm Tau T2A Node Pool with gVisor Sandbox Enabled ---

resource "google_container_node_pool" "arm_sandbox_nodes" {
  provider   = google-beta
  name       = "arm-sandbox-node-pool"
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = 2

  node_config {
    machine_type    = "t2a-standard-4" # Arm Tau T2A processor (64-bit Armv8.2-A)
    image_type      = "COS_CONTAINERD" # Container-Optimized OS with containerd (required for GKE Sandbox)
    service_account = google_service_account.gke_nodes.email

    # Enable gVisor Sandbox
    sandbox_config {
      sandbox_type = "gvisor"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    labels = {
      "mvcp.ai/node-type" = "arm-gvisor-sandbox"
    }

    tags = ["gke-node"]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
