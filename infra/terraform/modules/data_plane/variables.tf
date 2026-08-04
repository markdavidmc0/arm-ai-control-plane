variable "project_id" {
  type        = string
  description = "The GCP Project ID where data plane resources will be deployed."
}

variable "zone" {
  type        = string
  description = "The GCP zone for the node pools."
}

variable "cluster_name" {
  type        = string
  description = "The name of the GKE cluster."
}

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
