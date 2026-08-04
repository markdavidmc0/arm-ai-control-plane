variable "project_id" {
  type        = string
  description = "The GCP Project ID where control plane resources will be deployed."
}

variable "cluster_name" {
  type        = string
  description = "The name of the GKE cluster."
}

variable "control_plane_repository" {
  type        = string
  description = "GitHub repository for Control Plane CI/CD OIDC authentication."
  default     = "markdavidmc0/arm-ai-control-plane"
}

variable "workspace_repository" {
  type        = string
  description = "GitHub repository for Developer Workspace CI/CD OIDC authentication."
  default     = "markdavidmc0/arm-developer-workspace"
}
