#!/usr/bin/env bash
# ==============================================================================
# Pattern 1: Complete Automated GitHub App Bootstrap for ARC
# ==============================================================================

set -e

KEY_PATH="${HOME}/.ssh/arc-app.pem"
REPO_TARGET="markdavidmc0/arm-developer-workspace"
CONTROL_PLANE_REPO="https://github.com/markdavidmc0/arm-ai-control-plane"
TFVARS_FILE="terraform/terraform.tfvars"

echo "=== 🚀 Starting Automated ARC GitHub App Bootstrap ==="

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

# 1. Ensure GitHub CLI is installed
if ! command -v gh &> /dev/null; then
  echo "❌ Error: GitHub CLI ('gh') is not installed. Install via 'brew install gh'."
  exit 1
fi

# 2. Generate RSA Private Key if not present
if [ ! -f "${KEY_PATH}" ]; then
  echo "🔑 Generating new RSA Private Key for ARC at ${KEY_PATH}..."
  openssl genrsa -out "${KEY_PATH}" 2048
  chmod 600 "${KEY_PATH}"
  echo "✅ Private key generated with strict permissions (chmod 600)."
else
  echo "🔒 Using existing RSA private key at ${KEY_PATH}"
fi

# 3. Export private key in-memory for Terraform
export TF_VAR_github_app_private_key="$(cat "${KEY_PATH}")"

# 4. Check if IDs are ALREADY saved in terraform/terraform.tfvars
if [ -f "${TFVARS_FILE}" ]; then
  APP_ID=$(grep -E '^github_app_id[[:space:]]*=' "${TFVARS_FILE}" | cut -d'=' -f2 | tr -d ' "' || true)
  INSTALL_ID=$(grep -E '^github_app_installation_id[[:space:]]*=' "${TFVARS_FILE}" | cut -d'=' -f2 | tr -d ' "' || true)
fi

# 5. If IDs are missing, try gh api or prompt user directly
if [ -z "${APP_ID}" ] || [ -z "${INSTALL_ID}" ]; then
  echo "🔍 Querying GitHub for existing App installation..."
  INSTALLATIONS=$(gh api /user/installations 2>/dev/null || echo "[]")
  APP_ID=$(echo "${INSTALLATIONS}" | grep -o '"app_id":[0-9]*' | head -n1 | cut -d':' -f2 || true)
  INSTALL_ID=$(echo "${INSTALLATIONS}" | grep -o '"id":[0-9]*' | head -n1 | cut -d':' -f2 || true)
fi

# 6. If still missing, display clear steps and prompt for the IDs once
if [ -z "${APP_ID}" ] || [ -z "${INSTALL_ID}" ]; then
  echo ""
  echo "=========================================================================="
  echo "ℹ️  Existing App IDs not found in 'terraform/terraform.tfvars'."
  echo "   If you already created your GitHub App:"
  echo "   1. Find your App ID at: https://github.com/settings/apps"
  echo "   2. Find your Installation ID at: https://github.com/settings/installations"
  echo "=========================================================================="
  echo ""
  read -p "👉 Enter your GitHub App ID: " APP_ID
  read -p "👉 Enter your GitHub Installation ID: " INSTALL_ID

  cat <<EOF > "${TFVARS_FILE}"
project_id                 = "sovereign-ai-495715"
region                     = "us-central1"
zone                       = "us-central1-a"
github_target_repo          = "${REPO_TARGET}"
github_app_id               = "${APP_ID}"
github_app_installation_id  = "${INSTALL_ID}"
EOF
  echo "✅ Updated '${TFVARS_FILE}' automatically with App ID ${APP_ID} and Installation ID ${INSTALL_ID}!"
else
  echo "✅ Active GitHub App Installation Confirmed!"
  echo "   App ID: ${APP_ID}"
  echo "   Installation ID: ${INSTALL_ID}"
fi

# 7. Offer automatic terraform apply
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
