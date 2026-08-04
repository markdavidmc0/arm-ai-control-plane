output "node_service_account_email" {
  value       = google_service_account.gke_nodes.email
  description = "The email address of the dedicated GKE worker node service account."
}

output "node_pool_names" {
  value       = { for k, v in google_container_node_pool.pools : k => v.name }
  description = "Map of created GKE node pool names keyed by node pool identifier."
}
