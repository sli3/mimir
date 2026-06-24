"""Test CORS configuration in dashboard/server.py."""
from dashboard.server import socketio

_EXPECTED_ORIGINS = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

def test_cors_allowed_origins_is_explicit():
    """Verify CORS uses an explicit allowlist, not wildcard."""
    actual = socketio.server.eio.cors_allowed_origins
    assert actual == _EXPECTED_ORIGINS, f"CORS should be {_EXPECTED_ORIGINS}, got {actual}"

def test_cors_not_wildcard():
    """Verify CORS is NOT configured as wildcard ('*')."""
    actual = socketio.server.eio.cors_allowed_origins
    assert actual != "*", f"CORS wildcard detected: {actual}"