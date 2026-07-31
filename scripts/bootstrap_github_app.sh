#!/usr/bin/env bash
# ==============================================================================
# Dual-UX Automated GitHub App Bootstrap for ARC (Desktop & CI/CD)
# ==============================================================================
# Supports both:
# 1. Desktop Developer Mode: Smart .pem key detection from ~/Downloads, interactive prompts,
#    and optional 'terraform apply'.
# 2. Non-Interactive CI/CD Mode: Detects $CI / $GITHUB_ACTIONS, reads env vars, and
#    applies Terraform -auto-approve without keyboard prompts.
# ==============================================================================

set -e

KEY_PATH="${HOME}/.ssh/arc-app.pem"
REPO_TARGET="markdavidmc0/arm-developer-workspace"
TFVARS_FILE="terraform/terraform.tfvars"

echo "=== 🚀 Starting Automated ARC GitHub App Bootstrap ==="

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

# ------------------------------------------------------------------------------
# 1. Smart RSA Key Detection & Setup
# ------------------------------------------------------------------------------
# Check if user downloaded a GitHub App private key to ~/Downloads/
DOWNLOADED_KEY=$(ls -t ${HOME}/Downloads/*.private-key.pem 2>/dev/null | head -n1 || true)

if [ -f "${KEY_PATH}" ]; then
  echo "🔒 Using existing RSA private key at ${KEY_PATH}"
elif [ -n "${DOWNLOADED_KEY}" ] && [ -f "${DOWNLOADED_KEY}" ]; then
  echo "🔑 Detected downloaded GitHub App private key at: ${DOWNLOADED_KEY}"
  cp "${DOWNLOADED_KEY}" "${KEY_PATH}"
  chmod 600 "${KEY_PATH}"
  echo "✅ Copied key to ${KEY_PATH} with secure permissions (chmod 600)."
else
  echo "🔑 Generating new RSA Private Key at ${KEY_PATH}..."
  openssl genrsa -out "${KEY_PATH}" 2048
  chmod 600 "${KEY_PATH}"
  echo "✅ Private key generated with strict permissions (chmod 600)."
fi

# Export private key in-memory for Terraform
export TF_VAR_github_app_private_key="$(cat "${KEY_PATH}")"

# ------------------------------------------------------------------------------
# 2. Check for Existing App IDs in terraform.tfvars or Environment Variables
# ------------------------------------------------------------------------------
if [ -f "${TFVARS_FILE}" ]; then
  APP_ID=$(grep -E '^github_app_id[[:space:]]*=' "${TFVARS_FILE}" | cut -d'=' -f2 | tr -d ' "' || true)
  INSTALL_ID=$(grep -E '^github_app_installation_id[[:space:]]*=' "${TFVARS_FILE}" | cut -d'=' -f2 | tr -d ' "' || true)
fi

# Override from Environment Variables if set (e.g. in CI/CD)
APP_ID="${TF_VAR_github_app_id:-$APP_ID}"
INSTALL_ID="${TF_VAR_github_app_installation_id:-$INSTALL_ID}"

# ------------------------------------------------------------------------------
# 3. Mode Selection: Headless CI/CD vs. Guided Desktop UX
# ------------------------------------------------------------------------------
if [ -n "${CI}" ] || [ -n "${GITHUB_ACTIONS}" ]; then
  echo "🤖 CI/CD Environment Detected (Non-Interactive Mode)."
  
  if [ -z "${APP_ID}" ] || [ -z "${INSTALL_ID}" ]; then
    echo "❌ Error: 'TF_VAR_github_app_id' and 'TF_VAR_github_app_installation_id' must be set in CI secrets."
    exit 1
  fi

  cat <<EOF > "${TFVARS_FILE}"
project_id                 = "sovereign-ai-495715"
region                     = "us-central1"
zone                       = "us-central1-a"
github_target_repo          = "${REPO_TARGET}"
github_app_id               = "${APP_ID}"
github_app_installation_id  = "${INSTALL_ID}"
EOF

  echo "🚀 Executing non-interactive 'terraform apply -auto-approve'..."
  cd terraform
  terraform apply -auto-approve
  exit 0
fi

# ------------------------------------------------------------------------------
# 4. Guided Desktop Developer UX
# ------------------------------------------------------------------------------
if [ -z "${APP_ID}" ] || [ -z "${INSTALL_ID}" ]; then
  echo ""
  echo "=========================================================================="
  echo "ℹ️  GitHub App IDs not found in 'terraform/terraform.tfvars'."
  echo "   Find your App ID and Installation ID in your browser:"
  echo "   1. App ID link: https://github.com/settings/apps"
  echo "   2. Installation ID link: https://github.com/settings/installations"
  echo "=========================================================================="
  echo ""
  read -p "👉 Enter your GitHub App ID: " APP_ID
  read -p "👉 Enter your GitHub Installation ID: " INSTALL_ID
fi

cat <<EOF > "${TFVARS_FILE}"
project_id                 = "sovereign-ai-495715"
region                     = "us-central1"
zone                       = "us-central1-a"
github_target_repo          = "${REPO_TARGET}"
github_app_id               = "${APP_ID}"
github_app_installation_id  = "${INSTALL_ID}"
EOF

echo "✅ Updated '${TFVARS_FILE}' automatically with App ID ${APP_ID} and Installation ID ${INSTALL_ID}!"

echo ""
read -p "❓ Do you want to run 'terraform apply' now using the in-memory private key? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "🚀 Running 'terraform apply'..."
  cd terraform
  terraform apply
else
  echo "=== 📋 Manual Terraform Execution Instructions ==="
  echo "Run the following commands in your terminal whenever you wish to deploy:"
  echo "  export TF_VAR_github_app_private_key=\"\$(cat ~/.ssh/arc-app.pem)\""
  echo "  cd terraform && terraform apply"
  echo "=========================================================="
fi
