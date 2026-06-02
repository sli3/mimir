#!/usr/bin/env bash
# =============================================================================
# setup.sh — Mimir RF Scanner
# Environment setup for Linux (Fedora 44 and Ubuntu/Debian)
#
# LEGAL NOTICE
# This script installs receive-only SDR software.
# Jurisdiction: Australia — South Australia
# Law: Radiocommunications Act 1992 (Cth)
# Transmitting without an ACMA apparatus licence is a criminal offence.
# This script configures RX only. No TX software is installed.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No colour

info()    { echo -e "${BLUE}[mimir]${NC} $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "  ███╗   ███╗██╗███╗   ███╗██╗██████╗ "
echo "  ████╗ ████║██║████╗ ████║██║██╔══██╗"
echo "  ██╔████╔██║██║██╔████╔██║██║██████╔╝"
echo "  ██║╚██╔╝██║██║██║╚██╔╝██║██║██╔══██╗"
echo "  ██║ ╚═╝ ██║██║██║ ╚═╝ ██║██║██║  ██║"
echo "  ╚═╝     ╚═╝╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═╝"
echo ""
echo "  AI-Powered RF Spectrum Scanner — Passive RX Only"
echo "  Jurisdiction: Australia (SA) | Authority: ACMA"
echo "  Radiocommunications Act 1992 (Cth)"
echo ""

# ── Detect Linux distribution ─────────────────────────────────────────────────
detect_distro() {
    if command -v dnf &>/dev/null && [ -f /etc/fedora-release ]; then
        echo "fedora"
    elif command -v dnf &>/dev/null && [ -f /etc/redhat-release ]; then
        echo "rhel"
    elif command -v apt-get &>/dev/null && [ -f /etc/debian_version ]; then
        echo "debian"
    elif command -v apt-get &>/dev/null; then
        echo "ubuntu"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)
info "Detected distribution: ${DISTRO}"

# ── Install system packages ────────────────────────────────────────────────────
install_system_packages() {
    case "${DISTRO}" in
        fedora|rhel)
            info "Installing system packages via dnf..."
            sudo dnf install -y \
                hackrf \
                SoapySDR \
                python3-SoapySDR \
                gr-osmosdr \
                python3-pip \
                python3-devel
            success "System packages installed (Fedora/RHEL)"
            ;;
        debian|ubuntu)
            info "Installing system packages via apt..."
            sudo apt-get update
            sudo apt-get install -y \
                hackrf \
                libhackrf-dev \
                soapysdr-tools \
                libsoapysdr-dev \
                soapysdr-module-hackrf \
                python3-soapysdr \
                gr-osmosdr \
                python3-pip \
                python3-dev
            success "System packages installed (Debian/Ubuntu)"
            ;;
        unknown)
            error "Unsupported Linux distribution."
            error "This script supports Fedora (dnf) and Ubuntu/Debian (apt) only."
            error ""
            error "For Fedora, install manually:"
            error "  sudo dnf install hackrf SoapySDR python3-SoapySDR gr-osmosdr"
            error ""
            error "For Ubuntu/Debian, install manually:"
            error "  sudo apt-get install hackrf libhackrf-dev soapysdr-tools"
            error "  sudo apt-get install soapysdr-module-hackrf python3-soapysdr"
            exit 1
            ;;
    esac
}

# ── Configure udev rules ───────────────────────────────────────────────────────
# udev rules allow your user account to access USB devices without sudo.
# Without this, every hackrf_info or Python call would require root.
configure_udev() {
    info "Checking udev rules for HackRF..."

    RULES_FILE="/etc/udev/rules.d/53-hackrf.rules"

    if [ -f "${RULES_FILE}" ]; then
        success "udev rules already present: ${RULES_FILE}"
    else
        warn "udev rules not found. Installing..."
        # The official rules file from Great Scott Gadgets
        sudo bash -c "cat > ${RULES_FILE}" << 'EOF'
# HackRF One
ATTR{idVendor}=="1d50", ATTR{idProduct}=="6089", SYMLINK+="hackrf-one-%k", TAG+="uaccess"
# HackRF One (bootloader / DFU mode)  
ATTR{idVendor}=="1d50", ATTR{idProduct}=="6003", SYMLINK+="rad1o-%k", TAG+="uaccess"
EOF
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        success "udev rules installed."
        warn "You may need to unplug and replug the HackRF for rules to take effect."
    fi

    # Add user to plugdev group (needed on some systems)
    if groups "${USER}" | grep -q plugdev; then
        success "User '${USER}' already in plugdev group."
    else
        info "Adding user '${USER}' to plugdev group..."
        sudo usermod -aG plugdev "${USER}"
        warn "Group change requires logout/login to take effect."
    fi
}

# ── Install Python dependencies ────────────────────────────────────────────────
install_python_deps() {
    info "Installing Python dependencies..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
        pip install --user -r "${SCRIPT_DIR}/requirements.txt"
        success "Python dependencies installed."
    else
        warn "requirements.txt not found — skipping Python deps."
        warn "Run 'pip install numpy pytest' manually."
    fi
}

# ── Verify hardware (optional) ─────────────────────────────────────────────────
verify_hardware() {
    info "Verifying HackRF hardware..."
    if command -v hackrf_info &>/dev/null; then
        if hackrf_info 2>&1 | grep -q "Found HackRF"; then
            success "HackRF One detected and working."
        else
            warn "hackrf_info ran but no device found."
            warn "Make sure the HackRF is plugged in via USB with an antenna attached."
        fi
    else
        warn "hackrf_info not found — hardware verification skipped."
    fi
}

# ── Build React dashboard ─────────────────────────────────────────────────────
build_dashboard() {
    info "Building React dashboard..."
    if command -v npm &>/dev/null; then
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        cd "${SCRIPT_DIR}/dashboard" && npm install && npm run build && cd "${SCRIPT_DIR}"
        success "Dashboard built successfully."
    else
        warn "npm not found. React dashboard not built."
        warn "Install Node.js and run: cd dashboard && npm install && npm run build"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    install_system_packages
    configure_udev
    install_python_deps
    build_dashboard
    verify_hardware

    echo ""
    success "Mimir setup complete."
    echo ""
    info "Next steps:"
    echo "  1. Plug in the HackRF One with antenna attached"
    echo "  2. Run: hackrf_info"
    echo "  3. Run: python -m pytest tests/core/test_rx_only_lock.py -v"
    echo ""
    info "Project location: ~/Repository/mimir"
    echo ""
}

main
