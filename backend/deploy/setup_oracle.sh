#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# backend/deploy/setup_oracle.sh
#
# One-shot Oracle Cloud Always Free VM setup for the NeuralGTO FastAPI
# backend.  Run as a non-root user with sudo privileges (default ubuntu
# user on Oracle Cloud Ubuntu 22.04 image is fine).
#
# Usage:
#   chmod +x setup_oracle.sh
#   ./setup_oracle.sh
#
# What it does:
#   1. System update + essential packages
#   2. Python 3.13 via deadsnakes PPA
#   3. Clone neus_nlhe repo + install deps
#   4. Download TexasSolver Linux binary
#   5. Create .env template
#   6. Install + configure Cloudflare Tunnel (cloudflared)
#   7. Register systemd service
#
# After running:
#   - Fill in /opt/neuralgto/.env  (GEMINI_API_KEY etc.)
#   - Run: sudo systemctl start neuralgto-api
#   - Set up a Cloudflare Tunnel in the CF dashboard (see DEPLOYMENT.md)
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="https://github.com/adihebbalae/neus_nlhe.git"
INSTALL_DIR="/opt/neuralgto"
SERVICE_NAME="neuralgto-api"
PYTHON_VERSION="3.13"
TEXASSOLVER_VERSION="v0.2.0"
TEXASSOLVER_URL="https://github.com/bupticybee/TexasSolver/releases/download/${TEXASSOLVER_VERSION}/TexasSolver-${TEXASSOLVER_VERSION}-Linux.zip"
# SHA-256 of TexasSolver-v0.2.0-Linux.zip — verify against the release page
# before deploying: https://github.com/bupticybee/TexasSolver/releases/tag/v0.2.0
# Update this value if you change TEXASSOLVER_VERSION.
TEXASSOLVER_SHA256="FIXME_verify_sha256_from_github_release_page"

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[setup]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
die()     { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

# ── 0. Preflight ──────────────────────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] && die "Run as a regular user (not root). Script uses sudo internally."
command -v git &>/dev/null || die "git not found — install it manually first: sudo apt install -y git"

# ── 1. System update ──────────────────────────────────────────────────────
info "Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    curl wget unzip git software-properties-common \
    build-essential libssl-dev libffi-dev \
    nginx certbot python3-certbot-nginx

# ── 2. Python 3.13 via deadsnakes ─────────────────────────────────────────
if ! command -v python3.13 &>/dev/null; then
    info "Installing Python ${PYTHON_VERSION} via deadsnakes PPA..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        python3.13 python3.13-venv python3.13-dev
    # Use ensurepip (ships with Python 3.13) — avoids piping remote code to sudo.
    sudo python3.13 -m ensurepip --upgrade 2>/dev/null \
        || { warn "ensurepip unavailable; falling back to get-pip.py (verify your network)"; \
             curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.13; }
else
    info "Python 3.13 already installed: $(python3.13 --version)"
fi

# ── 3. Clone repo ─────────────────────────────────────────────────────────
info "Cloning neus_nlhe repo to ${INSTALL_DIR}..."
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    warn "Repo already exists — pulling latest instead."
    sudo git -C "${INSTALL_DIR}" pull origin main
else
    sudo git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

# Set ownership so the deploying user can manage files
sudo chown -R "$(id -un):$(id -gn)" "${INSTALL_DIR}"

# ── 4. Python virtual environment + dependencies ──────────────────────────
info "Creating venv and installing Python dependencies..."
cd "${INSTALL_DIR}"

python3.13 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate

pip install --quiet --upgrade pip wheel
pip install --quiet -r backend/requirements.oracle.txt

# Also install the local poker_gpt package so the backend can import it
pip install --quiet -e ".[dev]" 2>/dev/null || pip install --quiet -e . 2>/dev/null || true

deactivate

# ── 5. TexasSolver Linux binary ───────────────────────────────────────────
SOLVER_DIR="${INSTALL_DIR}/solver_bin/TexasSolver-${TEXASSOLVER_VERSION}-Linux"
if [[ ! -f "${SOLVER_DIR}/console_solver" ]]; then
    info "Downloading TexasSolver Linux binary..."
    mkdir -p "${SOLVER_DIR}"
    TMP_ZIP=$(mktemp /tmp/texassolver.XXXXXX.zip)
    curl -sL "${TEXASSOLVER_URL}" -o "${TMP_ZIP}"
    # Verify SHA-256 before unpacking (supply chain hardening).
    if [[ "${TEXASSOLVER_SHA256}" != FIXME* ]]; then
        echo "${TEXASSOLVER_SHA256}  ${TMP_ZIP}" | sha256sum --check --quiet \
            || { rm -f "${TMP_ZIP}"; die "TexasSolver zip SHA-256 mismatch — aborting."; }
    else
        warn "TEXASSOLVER_SHA256 is not set — skipping integrity check. Set it before production use."
    fi
    unzip -q "${TMP_ZIP}" -d "${SOLVER_DIR}"
    # Binary may be nested — find it and move to expected location
    SOLVER_BIN=$(find "${SOLVER_DIR}" -name "console_solver" -type f | head -1)
    if [[ -n "${SOLVER_BIN}" && "${SOLVER_BIN}" != "${SOLVER_DIR}/console_solver" ]]; then
        mv "${SOLVER_BIN}" "${SOLVER_DIR}/console_solver"
    fi
    chmod +x "${SOLVER_DIR}/console_solver"
    rm -f "${TMP_ZIP}"
    info "TexasSolver installed at ${SOLVER_DIR}/console_solver"
else
    info "TexasSolver binary already present — skipping download."
fi

# ── 6. .env template ──────────────────────────────────────────────────────
ENV_FILE="${INSTALL_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    info "Creating .env template at ${ENV_FILE}..."
    cat > "${ENV_FILE}" << 'EOF'
# NeuralGTO — Oracle Cloud Production Environment
# Fill in all values before starting the service.
# Never commit this file.

# ── Required ──────────────────────────────────────────────────────────────
GEMINI_API_KEY=your_gemini_api_key_here

# ── Optional overrides ────────────────────────────────────────────────────
NEURALGTO_DEBUG=0
NEURALGTO_SOLVER_TIMEOUT=120

# ── Backend CORS (comma-separated allowed origins) ────────────────────────
# Set this to your Cloudflare Pages URL after deploying the frontend.
# Examples:
#   https://neuralgto.pages.dev
#   https://neuralgto.com,https://www.neuralgto.com
ALLOWED_ORIGINS=https://neuralgto.pages.dev
EOF
    warn "Created .env template — EDIT IT NOW: nano ${ENV_FILE}"
else
    info ".env already exists — skipping template creation."
fi

# ── 7. cloudflared (Cloudflare Tunnel daemon) ─────────────────────────────
if ! command -v cloudflared &>/dev/null; then
    info "Installing cloudflared..."
    ARCH=$(dpkg --print-architecture)  # amd64 or arm64
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
    TMP_DEB=$(mktemp /tmp/cloudflared.XXXXXX.deb)
    curl -sL "${CF_URL}" -o "${TMP_DEB}"
    sudo dpkg -i "${TMP_DEB}"
    rm -f "${TMP_DEB}"
    info "cloudflared $(cloudflared --version) installed"
else
    info "cloudflared already installed: $(cloudflared --version)"
fi

# ── 8. systemd service ────────────────────────────────────────────────────
info "Installing systemd service: ${SERVICE_NAME}..."
sudo cp "${INSTALL_DIR}/backend/deploy/neuralgto-api.service" \
    "/etc/systemd/system/${SERVICE_NAME}.service"

# Patch install dir into the service file
sudo sed -i "s|/opt/neuralgto|${INSTALL_DIR}|g" \
    "/etc/systemd/system/${SERVICE_NAME}.service"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

# ── 9. Oracle Cloud firewall (iptables) ───────────────────────────────────
info "Opening Oracle Cloud iptables rules for port 8000..."
# Oracle VMs block all ingress by default via iptables REJECT rule.
# We need to poke a hole for the API port (or remove the REJECT rule for
# the cloudflared tunnel — see DEPLOYMENT.md for tunnel-only setup where
# port 8000 stays closed to the public internet).
if ! sudo iptables -C INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
    sudo netfilter-persistent save 2>/dev/null || \
        sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Fill in your Gemini API key:"
echo "     nano ${ENV_FILE}"
echo ""
echo "  2. Start the API server:"
echo "     sudo systemctl start ${SERVICE_NAME}"
echo "     sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "  3. Health check:"
echo "     curl http://localhost:8000/api/health"
echo ""
echo "  4. Set up Cloudflare Tunnel (see DEPLOYMENT.md §3):"
echo "     cloudflared tunnel login"
echo "     cloudflared tunnel create neuralgto-api"
echo ""
