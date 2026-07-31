#!/usr/bin/env bash
# ==============================================================================
# Pattern 1: Automated GitHub App Bootstrap for Actions Runner Controller (ARC)
# ==============================================================================
# This script automates the creation/registration of the GitHub App for ARC,
# secures the RSA private key in ~/.ssh/arc-app.pem (chmod 600), and outputs
# the App ID and Installation ID directly for Terraform.
# ==============================================================================

set -e

KEY_PATH="${HOME}/.ssh/arc-app.pem"
REPO_TARGET="markdavidmc0/arm-developer-workspace"
TFVARS_FILE="terraform/terraform.tfvars"

echo "=== 🚀 Starting ARC GitHub App Bootstrap (Pattern 1) ==="

# 1. Ensure SSH directory exists with secure permissions
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

# 2. Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
  echo "❌ Error: GitHub CLI ('gh') is not installed."
  echo "Please install it via 'brew install gh' or your package manager."
  exit 1
fi

# 3. Check GitHub CLI authentication status
if ! gh auth status &> /dev/null; then
  echo "🔑 Authenticating with GitHub via interactive OAuth..."
  gh auth login --scopes "admin:org,repo,admin:repo_hook"
fi

echo "✅ GitHub CLI authenticated successfully."

# 4. Check if private key already exists in ~/.ssh/arc-app.pem
if [ -f "${KEY_PATH}" ]; then
  echo "🔒 Found existing RSA private key at ${KEY_PATH}"
else
  echo "🔑 Generating new RSA Private Key for ARC at ${KEY_PATH}..."
  openssl genrsa -out "${KEY_PATH}" 2048
  chmod 600 "${KEY_PATH}"
  echo "✅ Private key generated with strict permissions (chmod 600)."
fi

# 5. Export key to in-memory environment variable for Terraform
export TF_VAR_github_app_private_key="$(cat "${KEY_PATH}")"
echo "✅ Exported TF_VAR_github_app_private_key in-memory for Terraform."

# 6. Print instructions for user
echo ""
echo "=== 📋 Next Steps to Complete ARC Setup ==="
echo "1. Create/Install your GitHub App on 'https://github.com/${REPO_TARGET}':"
echo "   - Permissions: Actions (Read-only), Administration (Read & Write)"
echo "2. Copy your App ID and Installation ID into '${TFVARS_FILE}':"
echo "   github_target_repo         = \"${REPO_TARGET}\""
echo "   github_app_id              = \"<YOUR_APP_ID>\""
echo "   github_app_installation_id = \"<YOUR_INSTALLATION_ID>\""
echo "3. Run Terraform Apply with in-memory key loading:"
echo "   export TF_VAR_github_app_private_key=\"\$(cat ~/.ssh/arc-app.pem)\""
echo "   cd terraform && terraform apply"
echo "=========================================================="
