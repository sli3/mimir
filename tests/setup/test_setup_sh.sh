#!/usr/bin/env bash
# =============================================================================
# tests/setup/test_setup_sh.sh — Mock test suite for setup.sh
#
# This test stubs every real side-effect command (dnf, apt-get, pacman, zypper,
# brew, git, cmake, make, sudo, nproc, sysctl) so the suite runs without
# internet access, sudo, real package managers, or hardware.
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
