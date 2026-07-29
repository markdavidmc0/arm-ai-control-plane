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
if [[ -f "${ROOT_DIR}/config/provision_config.json" ]]; then
    CONFIG_FILE="${ROOT_DIR}/config/provision_config.json"
else
    CONFIG_FILE="${ROOT_DIR}/provision_config.json"
fi

show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dry-run       Launch a local dry-run smoke test of the control-plane without spinning up GCP resources"
    echo "  --apply         Execute complete GCP infrastructure stand-up and deployment via recreate_cluster_dr.sh"
    echo "  --help          Show this instruction panel"
}

# --- Core Dependency Checks ---
check_dependency() {
    local cmd=$1
    if ! command -v "$cmd" &> /dev/null; then
        error "Dependency '$cmd' is missing but required. Please install it to proceed."
    fi
}

# Validate requirement tools
check_dependency python3
check_dependency gcloud
check_dependency kubectl

# --- Config File Integrity Validation ---
validate_config() {
    info "Validating configuration file: ${CONFIG_FILE}"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        error "Configuration file 'config/provision_config.json' was not found!\n\n  \033[1;33m[HOW TO FIX THIS]\033[0m\n  1. Create a local copy of your config template:\n     \033[1;36mcp config/provision_config.template.json config/provision_config.json\033[0m\n  2. Open \033[1;32mconfig/provision_config.json\033[0m and populate your project ID, region, and Tailscale keys.\n  3. Re-run your desired command (e.g., ./scripts/provision_and_test.sh --dry-run)"
    fi
}

# --- Load Config properties using Python ---
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
validate_config

# Load variables
PROJECT_ID=$(read_config_key "project_id")
REGION=$(read_config_key "region")
ZONE=$(read_config_key "zone")
CLUSTER_NAME=$(read_config_key "cluster_name")

if [[ -z "$PROJECT_ID" || -z "$CLUSTER_NAME" ]]; then
    error "Configuration properties inside provision_config.json are invalid or missing."
fi

# --- LOCAL DRY RUN SMOKE TESTING ---
if [[ "$MODE" == "dry-run" ]]; then
    info "Initiating high-fidelity local control-plane dry-run smoke tests..."
    
    PYTHON_CMD="python3"
    if [[ -f "${ROOT_DIR}/.venv/bin/python3" ]]; then
        PYTHON_CMD="${ROOT_DIR}/.venv/bin/python3"
    elif command -v uv &>/dev/null; then
        PYTHON_CMD="uv run python3"
    fi

    check_dependency "python3"
    ${PYTHON_CMD} -c "import fastapi, uvicorn, requests" &>/dev/null || {
        warn "Required python packages (fastapi, uvicorn, requests) not found in system environment."
        info "Installing dependencies inside user space..."
        pip3 install fastapi uvicorn requests --user
    }

    if command -v lsof &>/dev/null; then
        ZOMBIE_PID=$(lsof -t -i:8000 || echo "")
        if [[ -n "$ZOMBIE_PID" ]]; then
            warn "Detected pre-existing background process running on port 8000 (PID: ${ZOMBIE_PID})."
            info "Terminating conflicting process to establish a clean test sandbox..."
            kill -9 $ZOMBIE_PID 2>/dev/null || true
            sleep 1
        fi
    fi

    info "Spinning up local FastAPI Control Plane on Port 8000..."
    PYTHONPATH="${ROOT_DIR}" ${PYTHON_CMD} "${ROOT_DIR}/src/control_plane/main.py" &
    SERVER_PID=$!
    
    cleanup() {
        info "Stopping local FastAPI Control Plane (PID: ${SERVER_PID})...."
        kill -9 "$SERVER_PID" 2>/dev/null || true
    }
    trap cleanup EXIT

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

    info "Smoke Test 1: Fetching API status..."
    curl -s http://localhost:8000/api/v1/health | grep -q '"status":"healthy"' || error "Smoke Test 1: Health check failed."
    success "Smoke Test 1: Health Check PASS"

    info "Smoke Test 2: Triggering optimization compiler pipeline (Naive Stride code)..."
    RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d '{"code": "void naive_multiply() { for(int k=0; k<128; k++) { C[i][j] += A[i][k]; } }"}' http://localhost:8000/api/v1/optimize)
    TASK_ID=$(echo "$RESPONSE" | "${PYTHON_CMD}" -c "import sys, json; print(json.load(sys.stdin)['task_id'])")
    info "Task ID created: ${TASK_ID}"

    info "Smoke Test 3: Polling task compilation status..."
    STATUS="queued"
    for i in {1..5}; do
        sleep 1
        TASK_RES=$(curl -s "http://localhost:8000/api/v1/status/${TASK_ID}")
        STATUS=$(echo "$TASK_RES" | "${PYTHON_CMD}" -c "import sys, json; print(json.load(sys.stdin)['status'])")
        info "Current state: ${STATUS}"
        if [[ "$STATUS" == "completed" ]]; then
            break
        fi
    done

    if [[ "$STATUS" != "completed" ]]; then
        error "Task failed to complete in the expected time."
    fi
    success "Smoke Test 3: Sandbox Compilation & Polling PASS"

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

# --- FULL PRODUCTION GCP CLOUD PROVISIONING (DELEGATES TO RECREATE_CLUSTER_DR.SH) ---
info "Delegating cloud infrastructure deployment to recreate_cluster_dr.sh..."

export GCP_PROJECT_ID="${PROJECT_ID}"
export GCP_REGION="${REGION:-us-central1}"
export GCP_ZONE="${ZONE:-us-central1-a}"
export GKE_CLUSTER_NAME="${CLUSTER_NAME:-mvcp-gke-cluster}"

exec "${SCRIPTS_DIR}/recreate_cluster_dr.sh"
