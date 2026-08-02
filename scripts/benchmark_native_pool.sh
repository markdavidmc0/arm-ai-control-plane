#!/usr/bin/env bash
# Standup / Teardown Script for Native Arm Benchmark Node Pool

set -euo pipefail

ACTION=${1:-"status"}

case "$ACTION" in
  up)
    echo "[GKE] Provisioning Native Arm Node Pool (2 x t2a-standard-4)..."
    terraform -chdir=terraform apply -target=google_container_node_pool.arm_native_nodes[0] -auto-approve
    echo "[GKE] Native Arm Node Pool is READY for baseline benchmarking."
    ;;
  down)
    echo "[GKE] Destroying Native Arm Node Pool to eliminate idle compute costs..."
    terraform -chdir=terraform destroy -target=google_container_node_pool.arm_native_nodes[0] -auto-approve
    echo "[GKE] Native Arm Node Pool destroyed successfully."
    ;;
  status)
    echo "[GKE] Checking Native Arm Node Pool Status:"
    kubectl get nodes -l mvcp.ai/node-type=arm-native-baseline || echo "Native node pool not currently provisioned."
    ;;
  *)
    echo "Usage: $0 {up|down|status}"
    exit 1
    ;;
esac
