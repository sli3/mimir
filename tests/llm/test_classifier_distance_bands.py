"""Offline prompt checks for the 2026-11-26 Pluto distance calibration."""

from llm.classifier import SignalClassifier, _DISTANCE_SCALE_REFERENCE


def test_user_prompt_distance_band_boundaries() -> None:
    """Check each neighbour's label at and just above the calibrated bounds."""
    classifier = SignalClassifier(base_url="")
    cases = [
        (0.003, "strong match"),
        (0.0031, "possible match"),
        (0.008, "possible match"),
        (0.0081, "different signal type"),
        (0.012, "different signal type"),
        (0.0121, "novel signal — not closely matched to anything stored"),
    ]
    neighbours = [
        {"label": f"boundary_{index}", "distance": distance}
        for index, (distance, _) in enumerate(cases, start=1)
    ]

    prompt = classifier._build_user_prompt(fingerprint={}, neighbours=neighbours)
    neighbour_lines = [line for line in prompt.splitlines() if "Label:" in line]

    assert len(neighbour_lines) == len(cases)
    # Distances are rounded to three decimals; check the label on each row.
    for index, (line, (_, expected_label)) in enumerate(
        zip(neighbour_lines, cases), start=1
    ):
        assert line.startswith(f"  {index}. Label: boundary_{index} ")
        assert line.endswith(f"({expected_label})")


def test_system_prompt_novel_distance_cut_off() -> None:
    """Use the calibrated novel cut-off in the system instructions."""
    prompt = SignalClassifier(base_url="")._build_system_prompt()

    assert "above 0.012" in prompt
    assert "above 0.008" not in prompt


def test_distance_scale_reference_calibration() -> None:
    """Keep the reference bands and Pluto measurements on the current run."""
    expected_lines = (
        "  0.000 – 0.003 : Strong match   — almost certainly the same signal type",
        "  0.003 – 0.008 : Possible match — likely same type, moderate confidence",
        "  0.008 – 0.012 : Different type — known signal but different category",
        "  0.012+        : Novel signal   — does not closely match anything stored",
    )
    for line in expected_lines:
        assert line in _DISTANCE_SCALE_REFERENCE.splitlines()

    assert "Pluto captures (2026-11-26)" in _DISTANCE_SCALE_REFERENCE
    assert "0.0015" in _DISTANCE_SCALE_REFERENCE
    assert "0.0012" in _DISTANCE_SCALE_REFERENCE
    assert "0.0136" in _DISTANCE_SCALE_REFERENCE
    assert "0.000 – 0.005" not in _DISTANCE_SCALE_REFERENCE
    assert "2026-09-04" not in _DISTANCE_SCALE_REFERENCE
