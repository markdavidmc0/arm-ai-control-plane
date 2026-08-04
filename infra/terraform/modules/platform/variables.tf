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

variable "pods_cidr_range" {
  type        = string
  description = "CIDR block for GKE Pod secondary IP range."
  default     = "10.4.0.0/14"
}

variable "services_cidr_range" {
  type        = string
  description = "CIDR block for GKE Services secondary IP range."
  default     = "10.8.0.0/20"
}
