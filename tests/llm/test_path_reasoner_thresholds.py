"""Keep the frontend anomaly threshold paired with the backend rule."""

import re
from pathlib import Path

from llm.path_reasoner import _HIGH_TURN_RATE_DEG_PER_SEC


def test_frontend_high_turn_threshold_matches_backend():
    js_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard/frontend/src/components/PathPredictionPanel.jsx"
    )
    source = js_path.read_text(encoding="utf-8")
    match = re.search(
        r"HIGH_TURN_RATE_DEG_PER_SEC\s*=\s*([\d.]+)", source
    )
    assert match is not None
    frontend_value = float(match.group(1))
    assert _HIGH_TURN_RATE_DEG_PER_SEC == 3.0
    assert frontend_value == 3.0
    assert frontend_value == _HIGH_TURN_RATE_DEG_PER_SEC
