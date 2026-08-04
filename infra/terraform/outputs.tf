output "cluster_endpoint" {
  value       = module.platform.cluster_endpoint
  description = "The IP address of the GKE cluster control plane."
}

output "cluster_ca_certificate" {
  value       = module.platform.cluster_ca_certificate
  description = "Base64 encoded public certificate for the cluster CA."
  sensitive   = true
}

output "kubernetes_cluster_name" {
  value       = module.platform.cluster_name
  description = "The name of the GKE Cluster."
}

output "vpc_network_name" {
  value       = module.platform.vpc_network_name
  description = "The name of the VPC network created for the MVCP."
}

output "gateway_service_account" {
  value       = module.control_plane.gateway_service_account_email
  description = "The email address of the Control Plane Gateway Workload Identity service account."
}

output "workload_identity_provider" {
  value       = module.control_plane.workload_identity_provider_id
  description = "The full resource name of the GitHub Actions Workload Identity Provider."
}

output "active_node_pools" {
  value       = module.data_plane.node_pool_names
  description = "Map of active GKE node pool names keyed by node pool identifier."
}
