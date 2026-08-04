output "vpc_network_id" {
  value       = google_compute_network.vpc_network.id
  description = "The ID of the VPC network created for the MVCP."
}

output "vpc_network_name" {
  value       = google_compute_network.vpc_network.name
  description = "The name of the VPC network created for the MVCP."
}

output "vpc_network_self_link" {
  value       = google_compute_network.vpc_network.self_link
  description = "The self_link of the VPC network created for the MVCP."
}

output "subnet_self_link" {
  value       = google_compute_subnetwork.subnet.self_link
  description = "The self_link of the subnetwork created for the MVCP."
}

output "cluster_name" {
  value       = google_container_cluster.primary.name
  description = "The name of the GKE Cluster."
}

output "cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "The IP address of this GKE cluster control plane."
}

output "cluster_ca_certificate" {
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  description = "Base64 encoded public certificate for the cluster CA."
  sensitive   = true
}

output "artifact_registry_id" {
  value       = google_artifact_registry_repository.mcp_tools.id
  description = "The ID of the Artifact Registry repository created for MCP tools."
}
