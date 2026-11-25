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

# ── Build SoapyPlutoSDR plugin from source (Fedora/RHEL only) ──────────────────
# The SoapySDR Pluto plugin is not in Fedora/RHEL repos and needs a source build.
# Source: https://github.com/pothosware/SoapyPlutoSDR
# Requires: SoapySDR-devel and libiio-devel; libad9361-iio-devel is optional
# and enables AD9361 support.
#
# AU legal note: This plugin has transmit capability but enables receive-only
# SDR access to the ADALM-PLUTO here. No transmit functionality is configured
# or enabled.
build_soapyplutosdr() {
    info "Building SoapyPlutoSDR plugin from source..."
    info "(Not available in Fedora/RHEL dnf repos, must be built)"

    # Check registration case-insensitively before building and after install.
    if SoapySDRUtil --info 2>/dev/null | grep -qi "plutosdr"; then
        success "SoapyPlutoSDR plugin already registered, skipping build."
        return
    fi

    BUILD_DIR="/tmp/mimir-deps/SoapyPlutoSDR"
    mkdir -p "${BUILD_DIR}"
    git clone --depth=1 https://github.com/pothosware/SoapyPlutoSDR.git "${BUILD_DIR}/src"
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

    if SoapySDRUtil --info 2>/dev/null | grep -qi "plutosdr"; then
        success "SoapyPlutoSDR plugin installed and registered."
    else
        error "SoapyPlutoSDR build succeeded but plugin not detected by SoapySDRUtil."
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

# ── Install system packages, SDR plugins and acarsdec ─────────────────────────
# Fedora/RHEL builds both SDR plugins; other platforms get manual Pluto guidance.
install_system_packages() {
    case "${OS}" in

        fedora|rhel)
            info "Installing system packages via dnf..."
            sudo dnf install -y \
                hackrf \
                hackrf-devel \
                SoapySDR \
                SoapySDR-devel \
                libiio-devel \
                libad9361-iio-devel \
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
            build_soapyplutosdr
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
            warn "ADALM-PLUTO support needs SoapyPlutoSDR built from https://github.com/pothosware/SoapyPlutoSDR (no automatic install)."
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
            warn "ADALM-PLUTO support needs SoapyPlutoSDR built from https://github.com/pothosware/SoapyPlutoSDR (no automatic install)."
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
            warn "ADALM-PLUTO support needs SoapyPlutoSDR built from https://github.com/pothosware/SoapyPlutoSDR (no automatic install)."
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
            warn "ADALM-PLUTO support needs SoapyPlutoSDR built from https://github.com/pothosware/SoapyPlutoSDR (no automatic install)."
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
            warn "  - SoapyPlutoSDR plugin (with libiio): https://github.com/pothosware/SoapyPlutoSDR"
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
        if ! getent group plugdev >/dev/null 2>&1; then
            info "Group 'plugdev' does not exist on this system — creating it."
            sudo groupadd plugdev
        fi
        info "Adding user '${USER}' to plugdev group..."
        sudo usermod -aG plugdev "${USER}"
        warn "Group change requires logout/login (or unplug/replug HackRF) to take effect."
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
# Installs from pyproject.toml via uv into a project-local .venv (Python 3.11)
# for tests and dev tooling. The scanner, which starts the dashboard server,
# runs from .venv-scan instead.
install_python_deps() {
    info "Installing Python dependencies via uv (.venv)..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "${SCRIPT_DIR}"

    uv sync --all-extras
    success "Python dependencies installed into .venv via uv."
}

# ── Create the locked scanner venv on system Python ─────────────────────────
# --system-site-packages exposes system packages (needed for SoapySDR) and
# keeps the user site enabled, searched before the venv's locked packages.
# Every scanner and tool launch must pass -s to ignore ~/.local packages;
# the -I verification already excludes them. With the user site excluded,
# the venv's locked packages take precedence over system packages.
# SoapySDR has TX capability; verification only imports it and never opens
# a device. Mimir uses RX only.
#
# The venv holds no data and is safe to delete and recreate. This function
# never uninstalls anything from ~/.local or the system and never touches data/.
# Export uv.lock and sync explicitly into .venv-scan: uv sync may recreate a
# venv and drop --system-site-packages. Never recreate an existing venv here,
# because uv venv (0.11) wipes an existing directory.
#
# MIMIR_SETUP_DIR allows mock tests to redirect the project into a temp dir.
create_scanner_venv() {
    local MIMIR_SYSTEM_PYTHON="${MIMIR_SYSTEM_PYTHON:-/usr/bin/python3}"
    local SCRIPT_DIR="${MIMIR_SETUP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
    local SCAN_VENV EXPORT_FILE EXPECTED_VERSION VERIFY_OUTPUT

    # This must be the interpreter that owns the system SoapySDR bindings
    # (Fedora: /usr/lib64/python3.x/site-packages).
    if [[ ! -x "${MIMIR_SYSTEM_PYTHON}" ]]; then
        error "Scanner Python is not executable: ${MIMIR_SYSTEM_PYTHON}. Set MIMIR_SYSTEM_PYTHON to the interpreter with system SoapySDR bindings."
        exit 1
    fi

    if ! cd "${SCRIPT_DIR}"; then
        error "Could not enter the scanner project directory: ${SCRIPT_DIR}"
        exit 1
    fi
    SCRIPT_DIR="$(pwd)"
    SCAN_VENV="${SCRIPT_DIR}/.venv-scan"

    if [[ ! -f "${SCAN_VENV}/pyvenv.cfg" ]]; then
        info "Creating scanner venv with system packages: ${SCAN_VENV}"
        if ! uv venv --python "${MIMIR_SYSTEM_PYTHON}" --system-site-packages "${SCAN_VENV}"; then
            error "Could not create the scanner venv. See output above."
            exit 1
        fi
    else
        info "Scanner venv already exists, skipping creation: ${SCAN_VENV}"
    fi

    if ! EXPORT_FILE="$(mktemp /tmp/mimir-scanner-deps.XXXXXX.txt)"; then
        error "Could not create the temporary scanner requirements file."
        exit 1
    fi
    if ! uv export --frozen --format requirements-txt --no-dev --all-extras > "${EXPORT_FILE}"; then
        rm -f "${EXPORT_FILE}"
        error "uv export failed. Could not export the locked scanner dependencies from uv.lock."
        exit 1
    fi
    if ! uv pip sync --python "${SCAN_VENV}/bin/python" "${EXPORT_FILE}"; then
        rm -f "${EXPORT_FILE}"
        error "Could not install locked dependencies into the scanner venv. See output above."
        exit 1
    fi
    rm -f "${EXPORT_FILE}"

    if ! EXPECTED_VERSION="$(awk '/^name = "chromadb"$/ {getline; gsub(/"/, "", $3); print $3; exit}' "${SCRIPT_DIR}/uv.lock")" || [[ -z "${EXPECTED_VERSION}" ]]; then
        error "Could not read the expected ChromaDB version from uv.lock."
        exit 1
    fi
    # Isolated mode excludes the repo root and user site without opening SDRs.
    if ! VERIFY_OUTPUT="$("${SCAN_VENV}/bin/python" -I -c 'import SoapySDR; import chromadb; print(chromadb.__version__); print(chromadb.__file__)')"; then
        error "Scanner venv verification failed: could not import SoapySDR and ChromaDB."
        exit 1
    fi
    info "Scanner ChromaDB version and path:"
    echo "${VERIFY_OUTPUT}"
    if [[ "${VERIFY_OUTPUT%%$'\n'*}" != "${EXPECTED_VERSION}" ]]; then
        error "Scanner ChromaDB version mismatch: expected ${EXPECTED_VERSION} from uv.lock, got ${VERIFY_OUTPUT%%$'\n'*}."
        exit 1
    fi
    success "Scanner venv ready with locked dependencies: ${SCAN_VENV}"
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

# ── Show shell-independent launcher commands after setup ─────────────────────
# The launcher shows commands before running and isolates scanner Python imports.
print_next_steps() {
    info "Next steps:"
    echo "  1. Plug in the HackRF One or ADALM-PLUTO with an antenna attached"
    echo "  2. Check a HackRF with: hackrf_info"
    echo "  3. Run the tests: ./mimir test"
    echo "  4. Live scan: ./mimir scan (choose a device with --device hackrf or --device plutosdr)"
    echo "  5. Demo with no SDR: ./mimir demo"
    echo "  6. Tools: ./mimir tool lists them, ./mimir tool <name> runs one"
    echo ""
    echo "  ./mimir works the same from bash, zsh and fish, shows each command before running it,"
    echo "  and always adds -s so old ~/.local packages stay out."
    echo ""
    info "Dashboard: http://localhost:5000"
    echo ""
}

# ── Main: install environments and show launcher usage ────────────────────────
main() {
    install_system_packages
    configure_udev
    check_uv
    install_python_deps
    create_scanner_venv
    build_dashboard
    verify_hardware

    echo ""
    success "Mimir setup complete."
    echo ""
    print_next_steps
}

# Only run main when executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
