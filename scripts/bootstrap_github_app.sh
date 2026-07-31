#!/usr/bin/env bash
# ==============================================================================
# Pattern 1: Complete Automated GitHub App Bootstrap for ARC
# ==============================================================================
# This script automates GitHub App creation/querying, saves the RSA private key
# securely at ~/.ssh/arc-app.pem (chmod 600), updates terraform/terraform.tfvars,
# and offers 'terraform apply' ONLY after verifying that the App is installed.
# ==============================================================================

set -e

KEY_PATH="${HOME}/.ssh/arc-app.pem"
REPO_TARGET="markdavidmc0/arm-developer-workspace"
TFVARS_FILE="terraform/terraform.tfvars"

echo "=== 🚀 Starting Automated ARC GitHub App Bootstrap ==="

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

# 1. Ensure GitHub CLI is installed and authenticated
if ! command -v gh &> /dev/null; then
  echo "❌ Error: GitHub CLI ('gh') is not installed. Install via 'brew install gh'."
  exit 1
fi

if ! gh auth status &> /dev/null; then
  echo "🔑 Authenticating with GitHub via interactive OAuth..."
  gh auth login --scopes "admin:org,repo,admin:repo_hook"
fi

echo "✅ GitHub CLI authenticated successfully."

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

# 4. Check for active GitHub App installations via REST API
echo "🔍 Querying active GitHub App installations for ${REPO_TARGET}..."
INSTALLATIONS=$(gh api /user/installations 2>/dev/null || echo "[]")

APP_ID=$(echo "${INSTALLATIONS}" | grep -o '"app_id":[0-9]*' | head -n1 | cut -d':' -f2 || true)
INSTALL_ID=$(echo "${INSTALLATIONS}" | grep -o '"id":[0-9]*' | head -n1 | cut -d':' -f2 || true)

# 5. Populate terraform/terraform.tfvars if IDs are detected
if [ -n "${APP_ID}" ] && [ -n "${INSTALL_ID}" ]; then
  echo "✅ Detected active GitHub App Installation!"
  echo "   App ID: ${APP_ID}"
  echo "   Installation ID: ${INSTALL_ID}"

  cat <<EOF > "${TFVARS_FILE}"
project_id                 = "sovereign-ai-495715"
region                     = "us-central1"
zone                       = "us-central1-a"
github_target_repo          = "${REPO_TARGET}"
github_app_id               = "${APP_ID}"
github_app_installation_id  = "${INSTALL_ID}"
EOF
  echo "✅ Updated '${TFVARS_FILE}' automatically!"

  # 6. Offer automatic terraform apply ONLY when App IDs are confirmed!
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

else
  echo "⚠️  No active GitHub App installation detected for ${REPO_TARGET}."
  echo "   To complete setup, create and install your GitHub App on GitHub:"
  echo "   1. Open: https://github.com/settings/apps/new"
  echo "   2. App Name: arm-control-plane-arc"
  echo "   3. Homepage URL: https://github.com/markdavidmc0/arm-ai-control-plane"
  echo "   4. Permissions: Actions (Read-only), Administration (Read & Write)"
  echo "   5. Install the App on: https://github.com/${REPO_TARGET}"
  echo "   6. Re-run 'bash scripts/bootstrap_github_app.sh' after installing!"
  echo "🛑 Terraform execution blocked until GitHub App is installed."
fi
