#!/usr/bin/env bash
# =============================================================================
# setup.sh — Mimir RF Scanner
# Environment setup for Linux (Fedora, Ubuntu/Debian, Arch) and macOS
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

# ── Detect OS and distribution ────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)
            if command -v dnf &>/dev/null && [ -f /etc/fedora-release ]; then
                echo "fedora"
            elif command -v dnf &>/dev/null && [ -f /etc/redhat-release ]; then
                echo "rhel"
            elif command -v apt-get &>/dev/null && [ -f /etc/debian_version ]; then
                echo "debian"
            elif command -v apt-get &>/dev/null; then
                echo "ubuntu"
            elif command -v pacman &>/dev/null; then
                echo "arch"
            elif command -v zypper &>/dev/null; then
                echo "opensuse"
            else
                echo "unknown"
            fi
            ;;
        *) echo "unsupported" ;;
    esac
}

OS=$(detect_os)
info "Detected OS: ${OS}"

# ── Build acarsdec from source ────────────────────────────────────────────────
# acarsdec is an ACARS decoder (Aircraft Communications Addressing and
# Reporting System). It is not available in any Linux package manager and
# must be built from source. The binary is installed to /usr/local/bin/acarsdec.
#
# Source: https://github.com/f00b4r0/acarsdec
# The f00b4r0 fork is the actively maintained version (TLeconte is legacy).
#
# SoapySDR support is enabled automatically by cmake — no flag required.
# The cmake build detects libSoapySDR and links against it.
#
# AU legal note: ACARS operates in the VHF aviation band (118–136 MHz).
# Passive reception is legal under the Radiocommunications Act 1992 (Cth).
# AU primary ACARS frequencies: 129.125 MHz, 130.025 MHz.
build_acarsdec() {
    info "Building acarsdec from source (f00b4r0 fork)..."

    # Use a temporary build directory — cleaned up after install
    BUILD_DIR="/tmp/mimir-deps/acarsdec"

    if command -v acarsdec &>/dev/null; then
        success "acarsdec already installed at $(command -v acarsdec) — skipping build."
        return
    fi

    mkdir -p "${BUILD_DIR}"
    git clone --depth=1 https://github.com/f00b4r0/acarsdec.git "${BUILD_DIR}/src"
    mkdir -p "${BUILD_DIR}/build"
    cd "${BUILD_DIR}/build"
    cmake ../src

    # Use all available CPU cores for the build.
    # nproc is Linux-only; macOS uses sysctl.
    if command -v nproc &>/dev/null; then
        make -j"$(nproc)"
    else
        make -j"$(sysctl -n hw.logicalcpu)"
    fi

    sudo make install
    cd - > /dev/null

    # Clean up build directory
    rm -rf "${BUILD_DIR}"

    if command -v acarsdec &>/dev/null; then
        success "acarsdec installed to $(command -v acarsdec)"
    else
        error "acarsdec build succeeded but binary not found in PATH."
        error "Check that /usr/local/bin is in your PATH."
        exit 1
    fi
}

# ── Install system packages ────────────────────────────────────────────────────
install_system_packages() {
    case "${OS}" in

        fedora|rhel)
            info "Installing system packages via dnf..."
            sudo dnf install -y \
                hackrf \
                SoapySDR \
                SoapySDR-devel \
                python3-SoapySDR \
                gr-osmosdr \
                python3-pip \
                python3-devel \
                cmake \
                gcc \
                make \
                git
            success "System packages installed (Fedora/RHEL)"
            warn "IMPORTANT — Fedora/RHEL: SoapySDR-module-hackrf does NOT exist in dnf repos."
            warn "You must build the HackRF SoapySDR plugin from source before Mimir can use the HackRF:"
            warn "  https://github.com/pothosware/SoapyHackRF"
            build_acarsdec
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
                python3-dev \
                cmake \
                gcc \
                make \
                git
            success "System packages installed (Debian/Ubuntu)"
            build_acarsdec
            ;;

        arch)
            info "Installing system packages via pacman..."
            sudo pacman -Syu --noconfirm \
                hackrf \
                soapysdr \
                soapyhackrf \
                python \
                python-pip \
                cmake \
                gcc \
                make \
                git
            success "System packages installed (Arch Linux)"
            warn "python3-SoapySDR bindings on Arch may need to be built from source."
            warn "If 'import SoapySDR' fails, see: https://github.com/pothosware/SoapySDR/wiki/PythonSupport"
            build_acarsdec
            ;;

        opensuse)
            info "Installing system packages via zypper..."
            sudo zypper install -y \
                hackrf \
                SoapySDR \
                SoapySDR-devel \
                python3-SoapySDR \
                python3-pip \
                cmake \
                gcc \
                make \
                git
            success "System packages installed (openSUSE)"
            warn "If soapysdr-module-hackrf is not available in your repos, build from source:"
            warn "  https://github.com/pothosware/SoapyHackRF"
            build_acarsdec
            ;;

        macos)
            info "Detected macOS — using Homebrew..."
            if ! command -v brew &>/dev/null; then
                error "Homebrew not found. Install it first:"
                error "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                exit 1
            fi
            brew install hackrf soapysdr soapyhackrf cmake git
            success "System packages installed via Homebrew"
            warn "macOS: Python SoapySDR bindings are not installed by Homebrew."
            warn "You must build them from source:"
            warn "  https://github.com/pothosware/SoapySDR/wiki/PythonSupport"
            warn "udev rules are not needed on macOS (USB access handled by the OS)."
            build_acarsdec
            ;;

        unknown)
            warn "Could not detect your Linux distribution."
            warn "Please install the following manually before continuing:"
            warn "  - hackrf (libhackrf + tools)"
            warn "  - SoapySDR + development headers + Python bindings"
            warn "  - SoapyHackRF plugin: https://github.com/pothosware/SoapyHackRF"
            warn "  - acarsdec (build from source): https://github.com/f00b4r0/acarsdec"
            warn "    cmake + gcc + make + git required to build acarsdec"
            warn "Then re-run this script or install Python deps manually:"
            warn "  pip install -r requirements.txt"
            ;;

        unsupported)
            error "Unsupported operating system: $(uname -s)"
            error "Mimir supports Linux (Fedora, Ubuntu/Debian, Arch, openSUSE) and macOS."
            error "Windows is not supported."
            exit 1
            ;;
    esac
}

# ── Configure udev rules (Linux only) ─────────────────────────────────────────
# udev rules allow your user account to access USB devices without sudo.
# Not needed on macOS — USB access is handled by the OS automatically.
configure_udev() {
    if [[ "${OS}" == "macos" ]]; then
        return
    fi

    info "Checking udev rules for HackRF..."
    RULES_FILE="/etc/udev/rules.d/53-hackrf.rules"

    if [ -f "${RULES_FILE}" ]; then
        success "udev rules already present: ${RULES_FILE}"
    else
        warn "udev rules not found. Installing..."
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
        if [[ "${OS}" == "macos" ]]; then
            # macOS with Homebrew Python requires --break-system-packages or a venv
            # Try pip3 first; fall back with flag if PEP 668 blocks it
            if pip3 install --user -r "${SCRIPT_DIR}/requirements.txt" 2>/dev/null; then
                success "Python dependencies installed."
            else
                warn "pip3 --user install failed (PEP 668). Trying with --break-system-packages..."
                pip3 install --break-system-packages -r "${SCRIPT_DIR}/requirements.txt"
                success "Python dependencies installed."
            fi
        else
            pip install --user -r "${SCRIPT_DIR}/requirements.txt"
            success "Python dependencies installed."
        fi
    else
        warn "requirements.txt not found — skipping Python deps."
        warn "Run 'pip install -r requirements.txt' manually."
    fi
}

# ── Build React dashboard ─────────────────────────────────────────────────────
build_dashboard() {
    info "Building React dashboard..."
    if command -v npm &>/dev/null; then
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        cd "${SCRIPT_DIR}/dashboard/frontend" && npm install && npm run build && cd "${SCRIPT_DIR}"
        success "Dashboard built successfully."
    else
        warn "npm not found. React dashboard not built."
        warn "Install Node.js and run: cd dashboard/frontend && npm install && npm run build"
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
    echo "  4. Run: python scan.py"
    echo ""
    info "Dashboard: http://localhost:5000"
    echo ""
}

main