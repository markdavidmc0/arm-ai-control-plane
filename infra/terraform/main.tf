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

# 1. Base Platform Infrastructure Module
module "platform" {
  source       = "./modules/platform"
  project_id   = var.project_id
  region       = var.region
  zone         = var.zone
  cluster_name = var.cluster_name
}

# 2. Control Plane & Auth Module (Implicit DAG dependency on module.platform via cluster_name)
module "control_plane" {
  source       = "./modules/control_plane"
  project_id   = var.project_id
  cluster_name = module.platform.cluster_name
}

# 3. Dynamic Data Plane Module (Implicit DAG dependency on module.platform via cluster_name)
module "data_plane" {
  source       = "./modules/data_plane"
  project_id   = var.project_id
  zone         = var.zone
  cluster_name = module.platform.cluster_name
  node_pools   = var.node_pools
}
