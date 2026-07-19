output "cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "The IP address of this GKE cluster control plane."
}

output "kubernetes_cluster_name" {
  value       = google_container_cluster.primary.name
  description = "The name of the GKE Cluster."
}

output "vpc_network_name" {
  value       = google_compute_network.vpc_network.name
  description = "The name of the VPC network created for the MVCP."
}
