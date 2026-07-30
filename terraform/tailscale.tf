# --- Tailscale Infrastructure-as-Code Configuration ---

variable "tailscale_api_key" {
  type        = string
  description = "Tailscale API Key or OAuth Secret for IaC provisioning"
  default     = ""
  sensitive   = true
}

variable "tailscale_tailnet" {
  type        = string
  description = "Tailscale Tailnet domain name"
  default     = ""
}

provider "tailscale" {
  tailnet = var.tailscale_tailnet != "" ? var.tailscale_tailnet : null
  api_key = var.tailscale_api_key != "" ? var.tailscale_api_key : null
}

# --- Item B: MagicDNS Search Domain (arm.internal) as Code ---
resource "tailscale_dns_search_paths" "arm_internal" {
  count        = var.tailscale_api_key != "" ? 1 : 0
  search_paths = ["arm.internal"]
}

# --- Item C: Tailscale ACLs & Tag Owners as Code ---
resource "tailscale_acl" "platform_acl" {
  count = var.tailscale_api_key != "" ? 1 : 0
  acl   = jsonencode({
    tagOwners = {
      "tag:ci"            = ["group:devops"]
      "tag:platform-node" = ["group:devops"]
    }
    acls = [
      {
        action = "accept"
        src    = ["tag:ci"]
        dst    = ["tag:platform-node:80,443,8080,10000"]
      },
      {
        action = "accept"
        src    = ["group:devops"]
        dst    = ["*:*"]
      }
    ]
  })
}
