#!/usr/bin/env bash
# =============================================================================
# tests/setup/test_setup_sh.sh — Mock test suite for setup.sh
#
# This test stubs every real side-effect command (dnf, apt-get, pacman, zypper,
# brew, git, cmake, make, sudo, nproc, sysctl, uv and scanner Python) so the
# suite runs without internet access, sudo, real package managers, or hardware.
#
# Run: bash tests/setup/test_setup_sh.sh
# =============================================================================

# ── Call recording via temp file (shared across subshells) ─────────────────
CALLS_FILE="/tmp/mimir-test-calls.txt"

record_call() {
    echo "$1" >> "$CALLS_FILE"
}

clear_calls() {
    > "$CALLS_FILE"
}

call_contains() {
    grep -q "$1" "$CALLS_FILE"
}

# Stubs for package managers
sudo() {
    record_call "sudo $*"
    return 0
}

dnf() {
    record_call "dnf $*"
    return 0
}

apt-get() {
    record_call "apt-get $*"
    return 0
}

pacman() {
    record_call "pacman $*"
    return 0
}

zypper() {
    record_call "zypper $*"
    return 0
}

brew() {
    record_call "brew $*"
    return 0
}

# Record uv calls and create only fake venvs inside the scanner test fixture.
# Export emits dummy requirements; no branch invokes the real uv executable.
uv() {
    record_call "uv $*"
    case "$1" in
        venv)
            local venv_path="${@: -1}"
            [[ "${venv_path}" == "${MIMIR_SETUP_DIR}/.venv-scan" ]] || return 1
            mkdir -p "${venv_path}/bin" || return 1
            cp "${MIMIR_SETUP_DIR}/stub-python" "${venv_path}/bin/python" || return 1
            echo "include-system-site-packages = true" > "${venv_path}/pyvenv.cfg"
            ;;
        export)
            echo "chromadb==${SCANNER_STUB_VERSION}"
            ;;
        pip)
            [[ "$2" == "sync" ]] || return 1
            ;;
        *) return 1 ;;
    esac
}

# Stubs for build tools
git() {
    record_call "git $*"
    return 0
}

cmake() {
    record_call "cmake $*"
    return 0
}

make() {
    record_call "make $*"
    return 0
}

nproc() {
    record_call "nproc"
    echo "4"
    return 0
}

sysctl() {
    record_call "sysctl $*"
    echo "8"
    return 0
}

# ── Source setup.sh ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../setup.sh"
SETUP_LOCK_FILE="${SCRIPT_DIR}/../../uv.lock"

set -euo pipefail

# Remove real acarsdec from PATH so build_acarsdec runs its full path
# (it is installed at /usr/local/bin/acarsdec on the build machine)
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "usr/local/bin" | tr '\n' ':')
export PATH

# ── Test runner ────────────────────────────────────────────────────────────
FAILED=0
PASSED=0

assert_pass() {
    local name="$1"
    echo "PASS: $name"
    PASSED=$((PASSED + 1))
}

assert_fail() {
    local name="$1"
    echo "FAIL: $name"
    FAILED=$((FAILED + 1))
}

# Prepare an isolated project and executable shell stubs in each case's
# subshell. Its EXIT trap removes the fixture even when setup exits early.
prepare_scanner_fixture() {
    MIMIR_SETUP_DIR="$(mktemp -d /tmp/mimir-test-scanner.XXXXXX)" || return 1
    trap 'rm -rf "${MIMIR_SETUP_DIR}"' EXIT
    MIMIR_SYSTEM_PYTHON="${MIMIR_SETUP_DIR}/system-python"
    cp "${SETUP_LOCK_FILE}" "${MIMIR_SETUP_DIR}/uv.lock" || return 1
    SCANNER_STUB_VERSION="$(awk '/^name = "chromadb"$/ {getline; gsub(/"/, "", $3); print $3; exit}' "${MIMIR_SETUP_DIR}/uv.lock")" || return 1
    [[ -n "${SCANNER_STUB_VERSION}" ]] || return 1
    export SCANNER_STUB_VERSION
    export SCANNER_CALLS_FILE="${CALLS_FILE}"
    # This interpreter is checked for executability but must never be run.
    cat > "${MIMIR_SYSTEM_PYTHON}" <<'EOF'
#!/usr/bin/env bash
exit 99
EOF
    cat > "${MIMIR_SETUP_DIR}/stub-python" <<'EOF'
#!/usr/bin/env bash
# Mimic isolated import verification without invoking Python or SoapySDR.
[[ "$1" == "-I" && "$2" == "-c" ]] || exit 98
printf 'scanner-python %s\n' "$*" >> "${SCANNER_CALLS_FILE}"
printf '%s\n' "${SCANNER_STUB_VERSION}" "${0%/bin/python}/lib/chromadb/__init__.py"
EOF
    chmod +x "${MIMIR_SYSTEM_PYTHON}" "${MIMIR_SETUP_DIR}/stub-python"
}

# ── Test 1: fedora installs correct packages ─────────────────────────────────
OS="fedora"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "fedora installs correct packages and calls build_acarsdec"
else
    assert_fail "fedora installs correct packages and calls build_acarsdec"
fi

# ── Test 2: debian/ubuntu installs correct packages ──────────────────────────
OS="debian"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "debian/ubuntu installs correct packages and calls build_acarsdec"
else
    assert_fail "debian/ubuntu installs correct packages and calls build_acarsdec"
fi

# Also verify ubuntu block
OS="ubuntu"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "ubuntu block matches debian block"
else
    assert_fail "ubuntu block matches debian block"
fi

# ── Test 3: arch installs correct packages ───────────────────────────────────
OS="arch"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "arch installs correct packages and calls build_acarsdec"
else
    assert_fail "arch installs correct packages and calls build_acarsdec"
fi

# ── Test 4: opensuse installs correct packages ─────────────────────────────────
OS="opensuse"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "opensuse installs correct packages and calls build_acarsdec"
else
    assert_fail "opensuse installs correct packages and calls build_acarsdec"
fi

# ── Test 5: macos installs correct packages and calls build_acarsdec ─────────
OS="macos"
clear_calls
output=$(install_system_packages 2>&1) || true
if echo "$output" | grep -q "acarsdec"; then
    assert_pass "macos installs correct packages and calls build_acarsdec"
else
    assert_fail "macos installs correct packages and calls build_acarsdec"
fi

# ── Test 6: unsupported exits with code 1 ────────────────────────────────────
OS="unsupported"
clear_calls
if ! (install_system_packages > /dev/null 2>&1); then
    assert_pass "unsupported exits with code 1"
else
    assert_fail "unsupported exits with code 1"
fi

# ── Test 7: unknown exits with code 0 and mentions acarsdec ──────────────────
OS="unknown"
clear_calls
if (install_system_packages > /dev/null 2>&1); then
    unknown_ok=1
else
    unknown_ok=0
fi

output=$( (install_system_packages 2>&1) )
if echo "$output" | grep -q "acarsdec"; then
    unknown_acars=1
else
    unknown_acars=0
fi

if [ "$unknown_ok" -eq 1 ] && [ "$unknown_acars" -eq 1 ]; then
    assert_pass "unknown exits with code 0 and mentions acarsdec"
else
    assert_fail "unknown exits with code 0 and mentions acarsdec"
fi

# ── Test 8: build_acarsdec skips if already in PATH ──────────────────────────
FAKE_BIN_DIR="/tmp/mimir-test-fake-bin"
mkdir -p "$FAKE_BIN_DIR"
touch "$FAKE_BIN_DIR/acarsdec"
chmod +x "$FAKE_BIN_DIR/acarsdec"
export PATH="$FAKE_BIN_DIR:$PATH"
clear_calls
output=$(build_acarsdec 2>&1) || true
if ! call_contains "git"; then
    assert_pass "build_acarsdec skips when already in PATH"
else
    assert_fail "build_acarsdec skips when already in PATH"
fi
rm -rf "$FAKE_BIN_DIR"

# ── Test 9: build_acarsdec clones f00b4r0/acarsdec ───────────────────────────
# Ensure acarsdec is NOT in PATH for this test
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "mimir-test-fake-bin" | tr '\n' ':')
export PATH
clear_calls
output=$(build_acarsdec 2>&1) || true
if call_contains "f00b4r0/acarsdec"; then
    assert_pass "build_acarsdec clones f00b4r0/acarsdec"
else
    assert_fail "build_acarsdec clones f00b4r0/acarsdec"
fi

# ── Test 10: build_acarsdec uses nproc on Linux ──────────────────────────────
clear_calls
output=$(build_acarsdec 2>&1) || true
if call_contains "make -j4"; then
    assert_pass "build_acarsdec uses nproc -j4"
else
    assert_fail "build_acarsdec uses nproc -j4"
fi

# ── Test 11: fresh scanner venv uses system packages and the frozen lock ─────
clear_calls
if (
    prepare_scanner_fixture || exit 1
    create_scanner_venv || exit 1
    [[ "$(sed -n '1p' "${CALLS_FILE}")" == "uv venv --python ${MIMIR_SYSTEM_PYTHON} --system-site-packages ${MIMIR_SETUP_DIR}/.venv-scan" ]] || exit 1
    [[ "$(sed -n '2p' "${CALLS_FILE}")" == "uv export --frozen --format requirements-txt --no-dev --all-extras" ]] || exit 1
    [[ "$(sed -n '3p' "${CALLS_FILE}")" == "uv pip sync --python ${MIMIR_SETUP_DIR}/.venv-scan/bin/python "* ]] || exit 1
    call_contains '^scanner-python -I -c ' || exit 1
    requirements_file="$(awk '/^uv pip sync / {print $NF}' "${CALLS_FILE}")"
    [[ -n "${requirements_file}" && ! -e "${requirements_file}" ]]
) > /dev/null 2>&1; then
    assert_pass "fresh scanner venv uses system packages and frozen dependencies"
else
    assert_fail "fresh scanner venv uses system packages and frozen dependencies"
fi

# ── Test 12: existing scanner venv is synced without recreation ─────────────
clear_calls
if (
    prepare_scanner_fixture || exit 1
    uv venv --python "${MIMIR_SYSTEM_PYTHON}" --system-site-packages "${MIMIR_SETUP_DIR}/.venv-scan" || exit 1
    clear_calls
    create_scanner_venv || exit 1
    ! call_contains '^uv venv ' || exit 1
    call_contains "^uv pip sync --python ${MIMIR_SETUP_DIR}/.venv-scan/bin/python "
) > /dev/null 2>&1; then
    assert_pass "existing scanner venv skips creation and still syncs"
else
    assert_fail "existing scanner venv skips creation and still syncs"
fi

# ── Test 13: missing system interpreter fails before any uv call ────────────
clear_calls
if (
    prepare_scanner_fixture || exit 1
    MIMIR_SYSTEM_PYTHON="${MIMIR_SETUP_DIR}/missing-python"
    if (create_scanner_venv); then
        exit 1
    fi
    ! call_contains '^uv '
) > /dev/null 2>&1; then
    assert_pass "missing scanner interpreter fails without calling uv"
else
    assert_fail "missing scanner interpreter fails without calling uv"
fi

# ── Test 14: imported ChromaDB must match the version in uv.lock ────────────
clear_calls
if (
    prepare_scanner_fixture || exit 1
    SCANNER_STUB_VERSION="0.0.0-mismatch"
    if (create_scanner_venv); then
        exit 1
    fi
    call_contains '^scanner-python -I -c '
) > /dev/null 2>&1; then
    assert_pass "scanner ChromaDB version mismatch fails verification"
else
    assert_fail "scanner ChromaDB version mismatch fails verification"
fi

# ── Cleanup ────────────────────────────────────────────────────────────────────
rm -f "$CALLS_FILE"

# ── Summary ────────────────────────────────────────────────────────────────────
TOTAL=$((PASSED + FAILED))
echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "All $TOTAL tests passed."
    exit 0
else
    echo "$FAILED of $TOTAL tests failed."
    exit 1
fi
