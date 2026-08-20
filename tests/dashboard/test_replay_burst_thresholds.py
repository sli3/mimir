"""Paired-constant contract for the replay burst fade threshold."""

import re
from pathlib import Path

from core.pipeline.features import BURST_MARGIN_DB


def test_frontend_burst_margin_matches_backend():
    """Keep dashboard/frontend/src/pages/ReplayPage.jsx in lock-step with the
    backend ``BURST_MARGIN_DB`` value. If either side changes during a field
    session recalibration, this test forces the divergence into the open.
    """
    js_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard/frontend/src/pages/ReplayPage.jsx"
    )
    source = js_path.read_text(encoding="utf-8")
    match = re.search(r"BURST_MARGIN_DB\s*=\s*([\d.]+)", source)
    assert match is not None
    frontend_value = float(match.group(1))
    assert BURST_MARGIN_DB == 6.0
    assert frontend_value == 6.0
    assert frontend_value == BURST_MARGIN_DB
