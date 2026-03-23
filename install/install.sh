#!/usr/bin/env bash
set -Eeuo pipefail

# patrolbot installer
# Installs patrolbot into the current user's home directory and sets up systemd boot service.

APP_NAME="patrolbot"
SERVICE_NAME="patrolbot.service"

# ---------- pretty output ----------
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[1;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'
C_BOLD='\033[1m'

info()    { echo -e "${C_BLUE}[INFO]${C_RESET} $*"; }
ok()      { echo -e "${C_GREEN}[ OK ]${C_RESET} $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET} $*"; }
err()     { echo -e "${C_RED}[FAIL]${C_RESET} $*" >&2; }
step()    { echo -e "\n${C_CYAN}${C_BOLD}==>${C_RESET} ${C_BOLD}$*${C_RESET}"; }

trap 'err "Installer hit a problem on line $LINENO. Scroll up; the gremlin left fingerprints."' ERR

# ---------- figure out user/home ----------
if [[ "${EUID}" -eq 0 ]]; then
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        INSTALL_USER="${SUDO_USER}"
        INSTALL_HOME="$(eval echo "~${SUDO_USER}")"
    else
        err "Do not run this directly as root without sudo context."
        err "Run it as your normal user:  bash install.sh"
        exit 1
    fi
else
    INSTALL_USER="$(id -un)"
    INSTALL_HOME="${HOME}"
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_HOME}/${APP_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_DIR="${INSTALL_DIR}/config"
LOG_DIR="${INSTALL_DIR}/logs"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"
TMP_SERVICE="/tmp/${SERVICE_NAME}"

step "patrolbot installer starting"
info "Install user      : ${INSTALL_USER}"
info "Install home      : ${INSTALL_HOME}"
info "Source project    : ${PROJECT_DIR}"
info "Target install    : ${INSTALL_DIR}"
info "Service file      : ${SERVICE_PATH}"

# ---------- sanity checks ----------
step "Running sanity checks"

if [[ ! -f "${PROJECT_DIR}/app.py" ]]; then
    err "Could not find app.py in project root: ${PROJECT_DIR}"
    err "Run this script from the patrolbot project tree."
    exit 1
fi
ok "Project root looks valid"

if ! command -v python3 >/dev/null 2>&1; then
    err "python3 is not installed."
    exit 1
fi
ok "python3 found: $(command -v python3)"

if ! command -v systemctl >/dev/null 2>&1; then
    err "systemctl not found. This installer expects systemd."
    exit 1
fi
ok "systemd detected"

# ---------- warn about possible conflicts ----------
step "Checking for likely conflicts"

CONFLICTS_FOUND=0

if systemctl list-unit-files | grep -qiE 'adeept|picar|marsrover|webServer'; then
    warn "Found possible existing robot-related systemd units."
    systemctl list-unit-files | grep -iE 'adeept|picar|marsrover|webServer' || true
    CONFLICTS_FOUND=1
fi

if [[ -f /etc/rc.local ]] && grep -qiE 'adeept|picar|webServer|patrolbot|python.*app.py' /etc/rc.local; then
    warn "/etc/rc.local appears to contain robot/autostart entries."
    CONFLICTS_FOUND=1
fi

if pgrep -af 'webServer|Adeept|patrolbot|app.py' >/dev/null 2>&1; then
    warn "Found existing Python robot-ish processes:"
    pgrep -af 'webServer|Adeept|patrolbot|app.py' || true
    CONFLICTS_FOUND=1
fi

if [[ "${CONFLICTS_FOUND}" -eq 0 ]]; then
    ok "No obvious conflict monsters detected"
else
    warn "You may want to disable/remove old Adeept startup junk if weird GPIO behavior shows up."
fi

# ---------- apt deps ----------
step "Installing apt dependencies"

APT_PACKAGES=(
    python3
    python3-venv
    python3-pip
    python3-dev
    python3-gpiozero
    python3-lgpio
    python3-rpi.gpio
    python3-picamera2
    python3-libcamera
    i2c-tools
)

info "Updating apt package lists..."
sudo apt-get update

info "Installing packages: ${APT_PACKAGES[*]}"
sudo apt-get install -y "${APT_PACKAGES[@]}"

ok "APT dependencies installed"

# ---------- copy/update project ----------
step "Copying project into home directory"

mkdir -p "${INSTALL_DIR}"

info "Syncing files to ${INSTALL_DIR}"
if command -v rsync >/dev/null 2>&1; then
    rsync -a \
        --delete \
        --exclude 'venv' \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.git' \
        --exclude 'logs/*.log' \
        "${PROJECT_DIR}/" "${INSTALL_DIR}/"
else
    warn "rsync not found; falling back to cp -a"
    cp -a "${PROJECT_DIR}/." "${INSTALL_DIR}/"
fi

ok "Project files copied"

# ---------- preserve runtime config ----------
step "Preparing config and log directories"

mkdir -p "${CONFIG_DIR}" "${LOG_DIR}"

if [[ ! -f "${CONFIG_DIR}/runtime.yaml" ]]; then
    if [[ -f "${INSTALL_DIR}/config/runtime.yaml" ]]; then
        ok "runtime.yaml already present"
    else
        warn "runtime.yaml missing; creating a minimal one"
        cat > "${CONFIG_DIR}/runtime.yaml" <<'EOF'
# patrolbot runtime overrides
# This file is preserved across reinstalls.
EOF
    fi
else
    ok "Existing runtime.yaml preserved"
fi

ok "Config and log directories ready"

# ---------- venv ----------
step "Creating Python virtual environment"

if [[ -d "${VENV_DIR}" ]]; then
    warn "Removing existing venv so we can rebuild it with --system-site-packages"
    rm -rf "${VENV_DIR}"
fi

python3 -m venv --system-site-packages "${VENV_DIR}"
ok "Virtual environment created"

info "Upgrading pip/setuptools/wheel"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel

if [[ -f "${INSTALL_DIR}/requirements.txt" ]]; then
    info "Installing Python requirements"
    "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
    ok "Python requirements installed"
else
    warn "requirements.txt not found; skipping pip install"
fi

# ---------- ownership ----------
step "Fixing ownership"

sudo chown -R "${INSTALL_USER}:${INSTALL_USER}" "${INSTALL_DIR}"
ok "Ownership set to ${INSTALL_USER}:${INSTALL_USER}"

# ---------- service generation ----------
step "Installing systemd service"

cat > "${TMP_SERVICE}" <<EOF
[Unit]
Description=patrolbot robot control service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${INSTALL_USER}
Group=${INSTALL_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/app.py
Restart=always
RestartSec=3

# A little patience for startup / shutdown
TimeoutStartSec=30
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF

sudo cp "${TMP_SERVICE}" "${SERVICE_PATH}"
rm -f "${TMP_SERVICE}"

ok "Service written to ${SERVICE_PATH}"

# ---------- systemd reload/enable ----------
step "Reloading and enabling service"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
ok "Service enabled for boot"

# ---------- restart service ----------
step "Starting patrolbot service"

sudo systemctl restart "${SERVICE_NAME}"
sleep 2

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "patrolbot service is running"
else
    warn "patrolbot service did not come up cleanly"
    echo
    info "Try these commands for clues:"
    echo "  sudo systemctl status ${SERVICE_NAME} --no-pager -l"
    echo "  journalctl -u ${SERVICE_NAME} -b --no-pager"
    exit 1
fi

# ---------- final summary ----------
step "Install complete"

IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -n "${IP_ADDR}" ]]; then
    ok "Web UI should be reachable at: http://${IP_ADDR}:5000"
else
    warn "Could not determine IP address automatically"
    info "Try: hostname -I"
fi

echo
ok "patrolbot is installed"
info "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME} --no-pager -l"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
echo "  journalctl -u ${SERVICE_NAME} -f"
echo
warn "If LEDs or GPIO act weird, check for old Adeept services/scripts still running."
echo
ok "Done. Bob should now wake up with less drama."