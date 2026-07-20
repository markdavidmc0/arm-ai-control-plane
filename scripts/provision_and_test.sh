#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -euo pipefail

# Text color formatting helper functions
info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[1;32m[SUCCESS]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARNING]\033[0m $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; exit 1; }

# Re-orient directories: SCRIPT is in /scripts, ROOT is parent of scripts
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPTS_DIR}/.." && pwd)"
CONFIG_FILE="${ROOT_DIR}/provision_config.json"

show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dry-run       Launch a local dry-run smoke test of the control-plane without spinning up GCP resources"
    echo "  --apply         Execute complete GCP infrastructure stand-up, GKE registration, and live cloud smoke tests"
    echo "  --help          Show this instruction panel"
}

# --- Core Dependency Checks ---
check_dependency() {
    local cmd=$1
    if ! command -v "$cmd" &> /dev/null; then
        error "Dependency '$cmd' is missing but required. Please install it to proceed."
    fi
}

# --- Load Config properties using Python to avoid jq dependency issues ---
read_config_key() {
    local key=$1
    python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${key}'])" 2>/dev/null || echo ""
}

# --- Check Option arguments ---
MODE="help"
if [[ $# -gt 0 ]]; then
    case "$1" in
        --dry-run) MODE="dry-run" ;;
        --apply) MODE="apply" ;;
        --help) MODE="help" ;;
        *) error "Unknown argument: $1. Use --help to view options." ;;
    esac
fi

if [[ "$MODE" == "help" ]]; then
    show_help
    exit 0
fi

# Assert config file is present
if [[ ! -f "$CONFIG_FILE" ]]; then
    error "Configuration file 'provision_config.json' was not found!\n\n  \033[1;33m[HOW TO FIX THIS]\033[0m\n  1. Create a local copy of your config template:\n     \033[1;36mcp provision_config.template.json provision_config.json\033[0m\n  2. Open \033[1;32mprovision_config.json\033[0m and populate your project ID, region, and Tailscale keys.\n  3. Re-run your desired command (e.g., ./scripts/provision_and_test.sh --dry-run)"
fi

# Load variables
PROJECT_ID=$(read_config_key "project_id")
REGION=$(read_config_key "region")
ZONE=$(read_config_key "zone")
CLUSTER_NAME=$(read_config_key "cluster_name")
TS_AUTH_KEY=$(read_config_key "tailscale_auth_key")
DOCKER_IMAGE=$(read_config_key "docker_image_name")
BACKEND_IMAGE=$(read_config_key "backend_image_name")

if [[ -z "$PROJECT_ID" || -z "$CLUSTER_NAME" || -z "$TS_AUTH_KEY" ]]; then
    error "Configuration properties inside provision_config.json are invalid or missing."
fi

# --- LOCAL DRY RUN SMOKE TESTING ---
if [[ "$MODE" == "dry-run" ]]; then
    info "Initiating high-fidelity local control-plane dry-run smoke tests..."
    
    # Assert FastAPI, uvicorn and requests are installed
    check_dependency "python3"
    python3 -c "import fastapi, uvicorn, requests" &>/dev/null || {
        warn "Required python packages (fastapi, uvicorn, requests) not found in system environment."
        info "Installing dependencies inside user space..."
        pip3 install fastapi uvicorn requests --user
    }

    # Defensive Port-Cleanup: Detect and terminate any pre-existing zombie processes on port 8000
    if command -v lsof &>/dev/null; then
        ZOMBIE_PID=$(lsof -t -i:8000 || echo "")
        if [[ -n "$ZOMBIE_PID" ]]; then
            warn "Detected pre-existing background process running on port 8000 (PID: ${ZOMBIE_PID})."
            info "Terminating conflicting process to establish a clean test sandbox..."
            kill -9 $ZOMBIE_PID 2>/dev/null || true
            sleep 1
        fi
    fi

    # Start FastAPI control plane in the background
    info "Spinning up local FastAPI Control Plane on Port 8000..."
    PYTHONPATH="${ROOT_DIR}" python3 "${ROOT_DIR}/src/control_plane/main.py" &
    SERVER_PID=$!
    
    # Setup exit trap to clean up the backend process when the script finishes
    cleanup() {
        info "Stopping local FastAPI Control Plane (PID: ${SERVER_PID})...."
        kill -9 "$SERVER_PID" 2>/dev/null || true
    }
    trap cleanup EXIT

    # Poll server health check until ready
    info "Waiting for API server readiness..."
    READY=false
    for i in {1..10}; do
        if curl -s http://localhost:8000/api/v1/health &>/dev/null; then
            READY=true
            break
        fi
        sleep 1
    done

    if [[ "$READY" == "false" ]]; then
        error "Failed to contact local FastAPI Control Plane on port 8000."
    fi
    success "Local Control Plane is ready!"

    # 1. Hit /health
    info "Smoke Test 1: Fetching API status..."
    curl -s http://localhost:8000/api/v1/health | grep -q '"status":"healthy"' || error "Smoke Test 1: Health check failed."
    success "Smoke Test 1: Health Check PASS"

    # 2. Trigger Naive Optimize job
    info "Smoke Test 2: Triggering optimization compiler pipeline (Naive Stride code)..."
    RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d '{"code": "void naive_multiply() { for(int k=0; k<128; k++) { C[i][j] += A[i][k]; } }"}' http://localhost:8000/api/v1/optimize)
    TASK_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['task_id'])")
    info "Task ID created: ${TASK_ID}"

    # 3. Poll task status until complete
    info "Smoke Test 3: Polling task compilation status..."
    STATUS="queued"
    for i in {1..5}; do
        sleep 1
        TASK_RES=$(curl -s "http://localhost:8000/api/v1/status/${TASK_ID}")
        STATUS=$(echo "$TASK_RES" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
        info "Current state: ${STATUS}"
        if [[ "$STATUS" == "completed" ]]; then
            break
        fi
    done

    if [[ "$STATUS" != "completed" ]]; then
        error "Task failed to complete in the expected time."
    fi
    success "Smoke Test 3: Sandbox Compilation & Polling PASS"

    # 4. Check MCP translation
    info "Smoke Test 4: Dispatching Model Context Protocol JSON-RPC 2.0 tool list request..."
    MCP_RES=$(curl -s -X POST -H "Content-Type: application/json" -d '{"jsonrpc": "2.0", "id": 99, "method": "tools/list"}' http://localhost:8000/api/v1/mcp)
    echo "$MCP_RES" | grep -q '"tools"' || error "Smoke Test 4: MCP JSON-RPC protocol error."
    success "Smoke Test 4: MCP JSON-RPC Specification PASS"

    success "=========================================================="
    success "ALL LOCAL DRY-RUN SMOKE TESTS COMPLETED SUCCESSFULLY!"
    success "The control-plane operates flawlessly."
    success "=========================================================="
    exit 0
fi

# --- FULL PRODUCTION GCP CLOUD PROVISIONING ---
info "Executing cloud infrastructure provisioning steps..."

# Assert tools are present
check_dependency "gcloud"
check_dependency "kubectl"
check_dependency "docker"

# Detect OpenTofu or Terraform
TF_CMD="terraform"
if command -v tofu &> /dev/null; then
    TF_CMD="tofu"
elif ! command -v terraform &> /dev/null; then
    error "Neither 'terraform' nor 'tofu' are installed. Please install one to provision the cloud resources."
fi

# 1. Deploy GCP VPC & GKE Cluster
info "Applying cloud configurations using ${TF_CMD}..."
cd "${ROOT_DIR}/terraform"

# Generate tfvars dynamically
cat <<EOF > terraform.tfvars
project_id   = "${PROJECT_ID}"
region       = "${REGION}"
zone         = "${ZONE}"
cluster_name = "${CLUSTER_NAME}"
EOF

${TF_CMD} init
${TF_CMD} apply -auto-approve

# Extract GKE endpoint
CLUSTER_ENDPOINT=$(${TF_CMD} output -raw cluster_endpoint)
info "Provisioned GKE endpoint: ${CLUSTER_ENDPOINT}"

# 2. Get credentials
info "Linking kubectl to newly created GKE cluster..."
gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}"

# 3. Create Sandbox structures and Secret Identity Keys
info "Registering sandboxed RuntimeClass..."
kubectl apply -f "${ROOT_DIR}/k8s/runtime-class.yaml"

info "Creating Tailscale secure cryptographic secret keys..."
kubectl delete secret tailscale-secret --namespace default 2>/dev/null || true
kubectl create secret generic tailscale-secret --namespace default --from-literal=TS_AUTHKEY="${TS_AUTH_KEY}"

# 4. Build and Publish the sandbox and backend images
info "Building mobile compiler-profiler docker image (utilizing offline local cache)..."
docker build --pull=false -t "${DOCKER_IMAGE}" -f - "${ROOT_DIR}" <<EOF
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y python3 python3-pip clang g++ git cmake
RUN mkdir -p /opt/android-ndk /opt/kleidiai/include
COPY src/mock_workload/compile_and_profile.py /opt/compile_and_profile.py
EOF

info "Building control plane backend docker image..."
docker build -t "${BACKEND_IMAGE}" -f - "${ROOT_DIR}" <<EOF
FROM python:3.9-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic kubernetes requests
COPY src/ /app/src/
COPY config/ /app/config/
EXPOSE 8000
CMD ["uvicorn", "src.control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

info "Configuring docker credentials and publishing images..."
gcloud auth configure-docker --quiet
docker push "${DOCKER_IMAGE}"
docker push "${BACKEND_IMAGE}"

# 5. Deploy Control Plane onto GKE
info "Publishing Envoy ConfigMap..."
kubectl delete configmap mvcp-envoy-config 2>/dev/null || true
kubectl create configmap mvcp-envoy-config --from-file="${ROOT_DIR}/config/envoy.yaml"

info "Applying control plane manifests dynamically..."
# Replace image placeholders dynamically with actual config-defined image parameters
DEPLOY_MANIFEST=$(mktemp)
sed -e "s|gcr.io/sovereign-ai-495715/control-plane-backend:latest|${BACKEND_IMAGE}|g" \
    -e "s|gcr.io/sovereign-ai-495715/mobile-ndk-kleidiai:latest|${DOCKER_IMAGE}|g" \
    "${ROOT_DIR}/k8s/deployment.yaml" > "${DEPLOY_MANIFEST}"
kubectl apply -f "${DEPLOY_MANIFEST}"
rm "${DEPLOY_MANIFEST}"

kubectl apply -f "${ROOT_DIR}/k8s/service.yaml"

# 6. Wait for LoadBalancer and run final Cloud Smoke Tests
info "Waiting for GCP LoadBalancer IP mapping (this can take several minutes)..."
LOADBALANCER_IP=""
for i in {1..30}; do
    LOADBALANCER_IP=$(kubectl get svc mvcp-envoy-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -n "$LOADBALANCER_IP" ]]; then
        break
    fi
    sleep 10
done

if [[ -z "$LOADBALANCER_IP" ]]; then
    warn "LoadBalancer provisioning is taking longer than usual. Please check with: 'kubectl get svc'"
    success "Infrastructure is up! Follow instructions in README to execute curl checks."
    exit 0
fi

success "Control Plane exposed at: http://${LOADBALANCER_IP}:10000"

# Running Smoke tests against public load balancer with retry polling for GCP routing warm-up
info "Running live smoke tests on cloud endpoint (polling with retries for GCP routing warm-up)..."
SMOKE_PASS=false
for attempt in {1..12}; do
    HEALTH_STATUS=$(curl -s "http://${LOADBALANCER_IP}:10000/api/v1/health" || echo "")
    if [[ "$HEALTH_STATUS" == *'"status":"healthy"'* ]]; then
        SMOKE_PASS=true
        break
    fi
    info "Waiting for public routing to propagate (attempt ${attempt}/12)..."
    sleep 5
done

if [[ "$SMOKE_PASS" == "true" ]]; then
    success "GCP Live Smoke Test: PASS"
else
    error "GCP Live Smoke Test: FAILED. API server unreachable at public endpoint."
fi

success "=========================================================="
success "GCP MVCP AI ENGINEERING PLATFORM DEPLOYED SUCCESSFULLY!"
success "=========================================================="
