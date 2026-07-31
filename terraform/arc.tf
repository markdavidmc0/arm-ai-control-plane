# --- Actions Runner Controller (ARC) Configuration ---

variable "github_pat" {
  type        = string
  description = "Optional Personal Access Token (PAT). Leave blank for secretless Workload Identity OIDC."
  default     = ""
  sensitive   = true
}

variable "github_app_id" {
  type        = string
  description = "Optional GitHub App ID. Leave blank for secretless Workload Identity OIDC."
  default     = ""
}

variable "github_app_installation_id" {
  type        = string
  description = "Optional GitHub App Installation ID."
  default     = ""
}

variable "github_app_private_key" {
  type        = string
  description = "Optional GitHub App Private Key."
  default     = ""
  sensitive   = true
}

variable "github_target_repo" {
  type        = string
  description = "Target GitHub repository for ephemeral runner scale set"
  default     = "markdavidmc0/arm-developer-workspace"
}

# Namespace for ARC Controller
resource "kubernetes_namespace" "arc_systems" {
  metadata {
    name = "arc-systems"
  }
}

# Namespace for Ephemeral Runner Pods
resource "kubernetes_namespace" "arc_runners" {
  metadata {
    name = "arc-runners"
  }
}

# Deploy ARC Scale Set Controller via Official GitHub Helm Chart
resource "helm_release" "arc_controller" {
  name             = "arc-controller"
  repository       = "oci://ghcr.io/actions/actions-runner-controller-charts"
  chart            = "gha-runner-scale-set-controller"
  version          = "0.8.0"
  namespace        = kubernetes_namespace.arc_systems.metadata[0].name
  create_namespace = false

  values = [
    yamlencode({
      tolerations = [
        {
          key      = "kubernetes.io/arch"
          operator = "Equal"
          value    = "arm64"
          effect   = "NoSchedule"
        },
        {
          key      = "sandbox.gke.io/runtime"
          operator = "Equal"
          value    = "gvisor"
          effect   = "NoSchedule"
        }
      ]
    })
  ]

  depends_on = [
    google_container_node_pool.arm_sandbox_nodes
  ]
}

# Deploy AutoscalingRunnerSet for arm-developer-workspace
resource "helm_release" "arc_runner_set" {
  count            = (var.github_app_id != "" || var.github_pat != "") ? 1 : 0
  name             = "arm-developer-workspace-runner"
  repository       = "oci://ghcr.io/actions/actions-runner-controller-charts"
  chart            = "gha-runner-scale-set"
  version          = "0.8.0"
  namespace        = kubernetes_namespace.arc_runners.metadata[0].name
  create_namespace = false

  values = [
    yamlencode({
      listenerTemplate = {
        spec = {
          containers = [
            {
              name    = "listener"
              image   = "ghcr.io/actions/gha-runner-scale-set-controller:0.8.0"
              command = ["/ghalistener"]
            }
          ]
          tolerations = [
            {
              key      = "kubernetes.io/arch"
              operator = "Equal"
              value    = "arm64"
              effect   = "NoSchedule"
            },
            {
              key      = "sandbox.gke.io/runtime"
              operator = "Equal"
              value    = "gvisor"
              effect   = "NoSchedule"
            }
          ]
        }
      }
      template = {
        spec = {
          containers = [
            {
              name    = "runner"
              image   = "ghcr.io/actions/actions-runner:latest"
              command = ["/home/runner/run.sh"]
              env = [
                {
                  name  = "SSL_CERT_FILE"
                  value = "/etc/ssl/certs/combined-ca-bundle.crt"
                },
                {
                  name  = "REQUESTS_CA_BUNDLE"
                  value = "/etc/ssl/certs/combined-ca-bundle.crt"
                }
              ]
              volumeMounts = [
                {
                  name      = "combined-ca"
                  mountPath = "/etc/ssl/certs/combined-ca-bundle.crt"
                  subPath   = "ca-bundle.crt"
                  readOnly  = true
                }
              ]
            }
          ]
          volumes = [
            {
              name = "combined-ca"
              secret = {
                secretName = "combined-ca-bundle"
              }
            }
          ]
          hostAliases = [
            {
              ip        = "10.8.12.222"
              hostnames = ["keycloak.arm.internal", "gateway.arm.internal"]
            }
          ]
          tolerations = [
            {
              key      = "kubernetes.io/arch"
              operator = "Equal"
              value    = "arm64"
              effect   = "NoSchedule"
            },
            {
              key      = "sandbox.gke.io/runtime"
              operator = "Equal"
              value    = "gvisor"
              effect   = "NoSchedule"
            }
          ]
        }
      }
    })
  ]

  set {
    name  = "githubConfigUrl"
    value = "https://github.com/${var.github_target_repo}"
  }

  dynamic "set" {
    for_each = var.github_pat != "" ? [var.github_pat] : []
    content {
      name  = "githubConfigSecret.github_token"
      value = set.value
    }
  }

  dynamic "set" {
    for_each = var.github_app_id != "" ? [var.github_app_id] : []
    content {
      name  = "githubConfigSecret.github_app_id"
      value = set.value
    }
  }

  dynamic "set" {
    for_each = var.github_app_installation_id != "" ? [var.github_app_installation_id] : []
    content {
      name  = "githubConfigSecret.github_app_installation_id"
      value = set.value
    }
  }

  dynamic "set" {
    for_each = var.github_app_private_key != "" ? [var.github_app_private_key] : []
    content {
      name  = "githubConfigSecret.github_app_private_key"
      value = set.value
    }
  }

  set {
    name  = "minRunners"
    value = "0"
  }

  set {
    name  = "maxRunners"
    value = "5"
  }

  depends_on = [
    helm_release.arc_controller
  ]
}
