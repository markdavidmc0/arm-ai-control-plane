# --- Kubernetes Provider Setup linked to GKE Primary Cluster ---

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
}

# --- Multi-Document YAML Manifest Parsers ---
locals {
  keycloak_docs          = [for doc in split("\n---\n", file("${path.module}/../.platform/deployments/keycloak.yaml")) : yamldecode(doc) if length(trimspace(doc)) > 0]
  gateway_and_envoy_docs = [for doc in split("\n---\n", file("${path.module}/../.platform/deployments/gateway-and-envoy.yaml")) : yamldecode(doc) if length(trimspace(doc)) > 0]
  in_house_mcp_docs      = [for doc in split("\n---\n", file("${path.module}/../.platform/deployments/in-house-mcp-servers.yaml")) : yamldecode(doc) if length(trimspace(doc)) > 0]
}

# --- Apply Keycloak Identity Provider Deployment ---
resource "kubernetes_manifest" "keycloak" {
  count    = length(local.keycloak_docs)
  manifest = local.keycloak_docs[count.index]

  depends_on = [
    google_container_node_pool.arm_sandbox_nodes
  ]
}

# --- Apply Gateway and Envoy Edge Guard Deployments ---
resource "kubernetes_manifest" "gateway_and_envoy" {
  count    = length(local.gateway_and_envoy_docs)
  manifest = local.gateway_and_envoy_docs[count.index]

  depends_on = [
    kubernetes_manifest.keycloak
  ]
}

# --- Apply In-House Platform MCP Servers ---
resource "kubernetes_manifest" "in_house_mcp_servers" {
  count    = length(local.in_house_mcp_docs)
  manifest = local.in_house_mcp_docs[count.index]

  depends_on = [
    kubernetes_manifest.gateway_and_envoy
  ]
}
