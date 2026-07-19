variable "project_id" {
  type        = string
  description = "The GCP Project ID where resources will be deployed."
}

variable "region" {
  type        = string
  description = "The GCP region for the network and GKE cluster."
  default     = "us-central1"
}

variable "zone" {
  type        = string
  description = "The GCP zone for the primary node pool."
  default     = "us-central1-a"
}

variable "cluster_name" {
  type        = string
  description = "The name of the GKE Cluster."
  default     = "mvcp-gke-cluster"
}
