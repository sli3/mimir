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

# ── Build SoapyHackRF plugin from source (Fedora/RHEL only) ──────────────────
# The SoapySDR HackRF plugin does not exist in Fedora/RHEL dnf repos under
# any package name. It must be built from source.
#
# Source: https://github.com/pothosware/SoapyHackRF
# Requires: gcc-c++, hackrf-devel, SoapySDR-devel (all installed above)
#
# AU legal note: This plugin enables receive-only SDR access to the HackRF.
# No transmit functionality is configured or enabled.
build_soapyhackrf() {
    info "Building SoapyHackRF plugin from source..."
    info "(Not available in Fedora/RHEL dnf repos — must be built)"

    # Check if already installed and registered with SoapySDR
    if SoapySDRUtil --info 2>/dev/null | grep -q "hackrf"; then
        success "SoapyHackRF plugin already registered — skipping build."
        return
    fi

    BUILD_DIR="/tmp/mimir-deps/SoapyHackRF"
    mkdir -p "${BUILD_DIR}"
    git clone --depth=1 https://github.com/pothosware/SoapyHackRF.git "${BUILD_DIR}/src"
    mkdir -p "${BUILD_DIR}/build"
    cd "${BUILD_DIR}/build"
    cmake ../src

    if command -v nproc &>/dev/null; then
        make -j"$(nproc)"
    else
        make -j"$(sysctl -n hw.logicalcpu)"
    fi

    sudo make install
    sudo ldconfig
    cd - > /dev/null

    rm -rf "${BUILD_DIR}"

    if SoapySDRUtil --info 2>/dev/null | grep -q "hackrf"; then
        success "SoapyHackRF plugin installed and registered."
    else
        error "SoapyHackRF build succeeded but plugin not detected by SoapySDRUtil."
        error "Try: sudo ldconfig && SoapySDRUtil --info"
        exit 1
    fi
}

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
                hackrf-devel \
                SoapySDR \
                SoapySDR-devel \
                python3-SoapySDR \
                gr-osmosdr \
                python3-pip \
                python3-devel \
                cmake \
                gcc \
                gcc-c++ \
                make \
                git \
                nodejs22
            success "System packages installed (Fedora/RHEL)"
            build_soapyhackrf
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
                g++ \
                make \
                git \
                nodejs
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
                git \
                nodejs \
                npm
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
                gcc-c++ \
                make \
                git \
                nodejs22
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
            brew install hackrf soapysdr soapyhackrf cmake git node
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
            warn "  - hackrf (libhackrf + tools + dev headers)"
            warn "  - SoapySDR + development headers + Python bindings"
            warn "  - SoapyHackRF plugin: https://github.com/pothosware/SoapyHackRF"
            warn "  - acarsdec (build from source): https://github.com/f00b4r0/acarsdec"
            warn "    cmake + gcc + gcc-c++ + make + git required to build"
            warn "  - nodejs (for dashboard build)"
            warn "Then re-run this script, or install uv and run 'uv sync --all-extras' manually."
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

# ── Check for uv (Python dependency manager) ──────────────────────────────────
# Mimir uses uv to manage Python dependencies — see pyproject.toml, which is
# the single source of truth for all Python deps. A previous requirements.txt
# was removed: it was a stale, manually-maintained duplicate that drifted out
# of sync with pyproject.toml (e.g. missing pyais and pyModeS), causing import
# failures that were hard to diagnose. Do not reintroduce a parallel
# requirements.txt — if one is ever needed for a downstream tool, regenerate
# it on demand with: uv export --format requirements-txt > requirements.txt
check_uv() {
    if command -v uv &>/dev/null; then
        success "uv already installed ($(uv --version))."
        return
    fi

    warn "uv not found. Mimir uses uv to manage Python dependencies (dashboard, tests, etc.)."
    echo ""
    read -r -p "Install uv now via the official installer (curl | sh from astral.sh)? [y/N] " REPLY
    echo ""

    if [[ "${REPLY}" =~ ^[Yy]$ ]]; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh

        # The installer places uv in ~/.local/bin or ~/.cargo/bin depending on
        # version; export both so it's on PATH for the rest of this run.
        export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

        if command -v uv &>/dev/null; then
            success "uv installed ($(uv --version))."
        else
            error "uv install ran but 'uv' is still not on PATH in this shell."
            error "Open a new shell (or source your shell rc file) and re-run ./setup.sh"
            exit 1
        fi
    else
        error "uv is required to install Mimir's Python dependencies."
        error "Install it manually: https://docs.astral.sh/uv/getting-started/installation/"
        error "Then re-run ./setup.sh"
        exit 1
    fi
}

# ── Install Python dependencies (uv-managed venv) ─────────────────────────────
# Installs from pyproject.toml via uv into a project-local .venv. This is what
# the test suite (pytest, vitest-adjacent tooling) and dashboard/server.py run
# under.
install_python_deps() {
    info "Installing Python dependencies via uv (.venv)..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "${SCRIPT_DIR}"

    uv sync --all-extras
    success "Python dependencies installed into .venv via uv."
}

# ── Install Python dependencies into system Python (for scan.py) ─────────────
# scan.py is launched directly with the system 'python' interpreter, not via
# 'uv run' and not from the .venv — see AGENTS.md / project conventions. Its
# internal modules (modules/ais, modules/adsb, dashboard/server, embeddings/*,
# llm/*) transitively import most of the third-party packages listed in
# pyproject.toml (pyais, pyModeS, chromadb, flask-socketio, etc.), so the full
# dependency set needs to also be present in system Python, not just the venv.
#
# pyproject.toml has no [build-system] table, so Mimir is not set up as an
# installable package — `pip install .` would try to build a wheel and fail.
# Instead, we ask uv to export the resolved dependency list as a flat
# requirements list (straight from pyproject.toml/uv.lock — no separate
# package list to maintain here, so this can't drift the way the old
# requirements.txt did) and feed that to system pip directly.
#
# PEP 668 ("externally managed environment") blocks plain pip installs on
# modern distros — --break-system-packages is required and deliberate here.
install_system_python_deps() {
    info "Installing Python dependencies into system Python (required by scan.py)..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "${SCRIPT_DIR}"

    PIP_CMD="pip"
    if ! command -v pip &>/dev/null && command -v pip3 &>/dev/null; then
        PIP_CMD="pip3"
    fi

    EXPORT_FILE="$(mktemp /tmp/mimir-system-deps.XXXXXX.txt)"
    trap 'rm -f "${EXPORT_FILE}"' RETURN

    if uv export --format requirements-txt --no-dev --all-extras > "${EXPORT_FILE}" 2>/dev/null; then
        if "${PIP_CMD}" install --break-system-packages -r "${EXPORT_FILE}"; then
            success "System Python dependencies installed (resolved from pyproject.toml via uv export)."
        else
            error "pip install into system Python failed. See output above."
            error "Re-run manually: ${PIP_CMD} install --break-system-packages -r <(uv export --format requirements-txt --no-dev --all-extras)"
            exit 1
        fi
    else
        error "uv export failed — could not resolve dependency list from pyproject.toml."
        error "Run 'uv sync --all-extras' first, then re-run this script."
        exit 1
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
    check_uv
    install_python_deps
    install_system_python_deps
    build_dashboard
    verify_hardware

    echo ""
    success "Mimir setup complete."
    echo ""
    info "Next steps:"
    echo "  1. Plug in the HackRF One with antenna attached"
    echo "  2. Run: hackrf_info"
    echo "  3. Run tests (uv-managed venv): uv run pytest tests/core/test_rx_only_lock.py -v"
    echo "  4. Run the scanner (system Python, needs PYTHONPATH=. to find Mimir's own"
    echo "     packages — core/, modules/, dashboard/, embeddings/, llm/):"
    echo "       PYTHONPATH=. python scan.py"
    echo "  5. Diagnostic tools also need PYTHONPATH=., e.g.:"
    echo "       PYTHONPATH=. python tools/diagnose_threshold.py"
    echo ""
    info "Dashboard: http://localhost:5000"
    echo ""
}

# Only run main when executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi