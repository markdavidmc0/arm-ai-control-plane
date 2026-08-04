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

# --- GitHub OIDC Repositories ---

variable "control_plane_repository" {
  type        = string
  description = "GitHub repository (org/repo) for the control plane workflow authentication."
  default     = "markdavidmc0/arm-federated-ai-control-plane"
}

variable "workspace_repository" {
  type        = string
  description = "GitHub repository (org/repo) for the developer workspace runner binding."
  default     = "markdavidmc0/arm-developer-workspace"
}

# --- Data Plane Node Pools ---

variable "node_pools" {
  type = map(object({
    machine_type = string
    node_count   = number
    is_gvisor    = bool
    labels       = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  description = "Map of node pool configurations for Arm sandbox and baseline execution."
  default = {
    "gvisor-sandbox" = {
      machine_type = "t2a-standard-4"
      node_count   = 2
      is_gvisor    = true
      labels = {
        "mvcp.ai/node-type" = "arm-gvisor-sandbox"
      }
      taints = [
        {
          key    = "sandbox.gke.io/runtime"
          value  = "gvisor"
          effect = "NO_SCHEDULE"
        }
      ]
    }
    "native-baseline" = {
      machine_type = "t2a-standard-4"
      node_count   = 2
      is_gvisor    = false
      labels = {
        "mvcp.ai/node-type" = "arm-native-baseline"
      }
      taints = []
    }
  }
}
