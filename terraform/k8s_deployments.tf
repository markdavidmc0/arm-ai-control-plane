# --- Kubernetes Provider Setup linked to GKE Primary Cluster ---

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
}

# --- Apply Keycloak Identity Provider Deployment ---

resource "kubernetes_manifest" "keycloak" {
  manifest = yamldecode(file("${path.module}/../.platform/deployments/keycloak.yaml"))

  depends_on = [
    google_container_node_pool.arm_sandbox_nodes
  ]
}

# --- Apply Gateway and Envoy Edge Guard Deployments ---

resource "kubernetes_manifest" "gateway_and_envoy" {
  manifest = yamldecode(file("${path.module}/../.platform/deployments/gateway-and-envoy.yaml"))

  depends_on = [
    kubernetes_manifest.keycloak
  ]
}

# --- Apply In-House Platform MCP Servers (Arm MCP, Performix, Metis) ---

resource "kubernetes_manifest" "in_house_mcp_servers" {
  manifest = yamldecode(file("${path.module}/../.platform/deployments/in-house-mcp-servers.yaml"))

  depends_on = [
    kubernetes_manifest.gateway_and_envoy
  ]
}
