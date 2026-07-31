#!/usr/bin/env bash
# ==============================================================================
# Pattern 1: Fully Automated GitHub App Bootstrap for ARC
# ==============================================================================

set -e

KEY_PATH="${HOME}/.ssh/arc-app.pem"
REPO_TARGET="markdavidmc0/arm-developer-workspace"
TFVARS_FILE="terraform/terraform.tfvars"

echo "=== 🚀 Starting Automated ARC GitHub App Bootstrap (Pattern 1) ==="

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
  echo "🔑 Generating new RSA Private Key at ${KEY_PATH}..."
  openssl genrsa -out "${KEY_PATH}" 2048
  chmod 600 "${KEY_PATH}"
  echo "✅ Private key generated."
else
  echo "🔒 Using existing RSA private key at ${KEY_PATH}"
fi

# 3. Export key in-memory for Terraform
export TF_VAR_github_app_private_key="$(cat "${KEY_PATH}")"

# 4. Fetch or Query existing GitHub App Installations
echo "🔍 Checking for existing GitHub App installations for ${REPO_TARGET}..."
INSTALLATIONS=$(gh api /user/installations 2>/dev/null || echo "[]")

APP_ID=$(echo "${INSTALLATIONS}" | grep -o '"app_id":[0-9]*' | head -n1 | cut -d':' -f2 || true)
INSTALL_ID=$(echo "${INSTALLATIONS}" | grep -o '"id":[0-9]*' | head -n1 | cut -d':' -f2 || true)

if [ -n "${APP_ID}" ] && [ -n "${INSTALL_ID}" ]; then
  echo "✅ Detected active GitHub App Installation!"
  echo "   App ID: ${APP_ID}"
  echo "   Installation ID: ${INSTALL_ID}"
else
  echo "ℹ️  To complete App creation on GitHub:"
  echo "   1. Open: https://github.com/settings/apps/new"
  echo "   2. App Name: arm-control-plane-arc"
  echo "   3. Homepage URL: https://github.com/markdavidmc0/arm-ai-control-plane"
  echo "   4. Permissions: Actions (Read-only), Administration (Read & Write)"
  echo "   5. Upload Public Key from: ${KEY_PATH}.pub (or paste generated PEM)"
fi

# 5. Append/Update terraform.tfvars if App ID was found
if [ -n "${APP_ID}" ] && [ -n "${INSTALL_ID}" ]; then
  cat <<EOF > "${TFVARS_FILE}"
project_id                 = "sovereign-ai-495715"
region                     = "us-central1"
zone                       = "us-central1-a"
github_target_repo          = "${REPO_TARGET}"
github_app_id               = "${APP_ID}"
github_app_installation_id  = "${INSTALL_ID}"
EOF
  echo "✅ Updated '${TFVARS_FILE}' automatically with App ID ${APP_ID} and Installation ID ${INSTALL_ID}!"
fi

echo ""
echo "=== 🚀 Ready to Deploy ARC via Terraform ==="
echo "Run the following command to deploy in-memory:"
echo "  export TF_VAR_github_app_private_key=\"\$(cat ~/.ssh/arc-app.pem)\""
echo "  cd terraform && terraform apply"
echo "=========================================================="
