"""
Tests for tools/capture_to_vectorstore.py

Capture tests mock both hardware paths and use temporary ChromaDB stores.
Console tests use fake SoapySDR bindings and restore logging after each case.
"""

import argparse
import io
import logging
import sys
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from types import ModuleType
import numpy as np
import pytest
from unittest.mock import MagicMock, call, patch

from embeddings.store import SignalStore
from dashboard.shared_state import BAND_PROFILES
from tools import _console, capture_to_vectorstore
from tools.capture_to_vectorstore import (
    ANTENNA_PROFILES,
    CAPTURE_TARGETS,
    build_metadata,
    run_capture_loop,
)


@pytest.fixture(autouse=True)
def restore_console_logging() -> Iterator[None]:
    """Restore pytest's handlers and logger levels after CLI logging setup."""
    root = logging.getLogger()
    handlers, root_level = root.handlers[:], root.level
    names = (
        capture_to_vectorstore.__name__, "core", "embeddings", "llm",
        "tools", "chromadb",
    )
    levels = {name: logging.getLogger(name).level for name in names}
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(root_level)
        for name, level in levels.items():
            logging.getLogger(name).setLevel(level)


def test_capture_targets_structure():
    required_keys = {
        "label",
        "freq_hz",
        "sample_rate_hz",
        "num_samples",
        "lna_gain_db",
        "vga_gain_db",
        "signal_threshold_db",
        "captures",
    }
    assert len(CAPTURE_TARGETS) == 7
    for target in CAPTURE_TARGETS:
        assert required_keys.issubset(set(target.keys()))
        assert isinstance(target["label"], str)
        assert isinstance(target["freq_hz"], int)
        assert isinstance(target["sample_rate_hz"], int)
        assert isinstance(target["num_samples"], int)
        assert isinstance(target["lna_gain_db"], int)
        assert isinstance(target["vga_gain_db"], int)
        assert isinstance(target["signal_threshold_db"], float)
        assert isinstance(target["captures"], int)
        assert target["sample_rate_hz"] == 2_000_000
        assert target["num_samples"] == 256_000
        assert target["captures"] == 5


def test_antenna_profiles_coverage():
    all_labels = {t["label"] for t in CAPTURE_TARGETS}
    for key, profile in ANTENNA_PROFILES.items():
        for band in profile["bands"]:
            assert band in all_labels, f"Antenna {key} band {band!r} not in CAPTURE_TARGETS"


def test_no_missing_signal_threshold():
    labels = {t["label"] for t in CAPTURE_TARGETS}
    for profile in ANTENNA_PROFILES.values():
        for band in profile["bands"]:
            assert band in labels
            target = next(t for t in CAPTURE_TARGETS if t["label"] == band)
            assert isinstance(target["signal_threshold_db"], float)


def test_build_metadata():
    target = {
        "freq_hz": 98_900_000,
        "sample_rate_hz": 2_000_000,
        "signal_threshold_db": BAND_PROFILES["fm_broadcast"]["signal_threshold_db"],
    }
    fingerprint = {
        "peak_power_db": -45.5,
        "snr_db": 18.3,
    }
    metadata = build_metadata("FM_broadcast", "Telescopic whip", target, fingerprint, 2)

    assert metadata["label"] == "FM_broadcast"
    assert metadata["source"] == "live_capture"
    assert metadata["antenna"] == "Telescopic whip"
    assert metadata["freq_hz"] == 98_900_000
    assert metadata["sample_rate_hz"] == 2_000_000
    assert metadata["capture_origin"] == "Adelaide, SA, AU"
    assert metadata["signal_threshold_db"] == BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]
    assert isinstance(metadata["timestamp"], str)
    assert metadata["peak_power_db"] == -45.5
    assert metadata["snr_db"] == 18.3
    assert metadata["capture_index"] == 2


def test_one_band_captures_five_records(tmp_path: Path) -> None:
    """Store five captures and metadata with the noise gate accepting samples.

    The constant IQ fixture is noise-shaped, so mock the gate to isolate storage.
    """
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "FM_broadcast")

    samples = np.ones(target["num_samples"], dtype=np.complex64)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.time.sleep") as mock_sleep,
        patch(
            "tools.capture_to_vectorstore.SignalClassifier.is_noise_shaped",
            return_value=False,
        ),
    ):
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=mock_sleep,
        )

    assert captured == 5
    assert store.count() == 5
    for meta in store._collection.get(include=["metadatas"])["metadatas"]:
        assert meta["label"] == "FM_broadcast"
        assert meta["source"] == "live_capture"


def test_runtime_error_stops_band_at_first_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Stop at the first error, printing it once without a wait or stderr log.

    A later capture would succeed, but must never be attempted for this band.
    """
    capture_to_vectorstore._configure_console_logging(False)
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "Aviation_VHF")
    samples = np.ones(target["num_samples"], dtype=np.complex64)

    call_count = 0

    def flaky_capture(**kwargs: object) -> np.ndarray:
        """Fail once and return samples only if incorrectly called again."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("HackRF not found")
        return samples

    with (
        patch("tools.capture_to_vectorstore.capture_iq", side_effect=flaky_capture),
        patch(
            "tools.capture_to_vectorstore.SignalClassifier.is_noise_shaped",
            return_value=False,
        ),
    ):
        sleep = MagicMock()
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=sleep,
        )

    assert call_count == 1
    assert captured == 0
    assert store.count() == 0
    sleep.assert_not_called()
    output = capsys.readouterr()
    assert "✗ capture 1/5 failed" in output.out
    assert output.out.count("HackRF not found") == 1
    assert output.err == ""


def test_wipe_flag_deletes_collection(tmp_path: Path) -> None:
    """Preserve collection deletion and reinitialisation before capturing."""
    mock_store = MagicMock(spec=SignalStore)
    mock_store.count.return_value = 7

    def fresh_mock(*args: object, **kwargs: object) -> MagicMock:
        """Return the fake store for each initialisation."""
        return mock_store

    with (
        # Mirror every attribute main() reads, with the production defaults
        # from _parse_args(), including quiet output and unset overrides.
        patch("tools.capture_to_vectorstore._parse_args", return_value=argparse.Namespace(
            wipe=True, device="hackrf", band=None, freq_mhz=None, captures=None,
            verbose=False,
        )),
        patch("tools.capture_to_vectorstore.Path", return_value=tmp_path),
        patch("tools.capture_to_vectorstore._quiet_soapy_info_logs"),
        patch("tools.capture_to_vectorstore.SignalStore", side_effect=fresh_mock),
        patch("tools.capture_to_vectorstore.SpectrumEmbedder"),
        patch("tools.capture_to_vectorstore._select_antenna", return_value=("1", ANTENNA_PROFILES["1"])),
        patch("tools.capture_to_vectorstore.run_capture_loop", return_value=0) as mock_loop,
    ):
        capture_to_vectorstore.main()

    assert mock_store.delete_collection.call_count == 1
    assert mock_loop.call_count == 1


def test_ctrl_c_at_band_card_skips_band(tmp_path: Path) -> None:
    """Skip the card's sole prompt without attempting any capture."""
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "ADS_B")
    samples = np.ones(target["num_samples"], dtype=np.complex64)

    call_count = 0

    def raising_input(_prompt: str) -> str:
        """Interrupt the single band-card prompt."""
        nonlocal call_count
        call_count += 1
        raise KeyboardInterrupt

    with patch(
        "tools.capture_to_vectorstore.capture_iq", return_value=samples,
    ) as capture:
        captured = run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Spiral discone",
            input_func=raising_input,
            sleep_func=lambda _secs: None,
        )

    assert call_count == 1
    capture.assert_not_called()
    assert captured == 0
    assert store.count() == 0


def test_signal_threshold_passed_and_stored(tmp_path: Path) -> None:
    """Forward and store the band's threshold while the noise gate accepts.

    Keep the real fingerprint call to verify threshold forwarding; mock only
    the noise gate so the constant IQ fixture reaches metadata storage.
    """
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    target = next(t for t in CAPTURE_TARGETS if t["label"] == "APRS")
    samples = np.ones(target["num_samples"], dtype=np.complex64)
    expected_threshold = target["signal_threshold_db"]

    real_fingerprint_spectrum = capture_to_vectorstore.fingerprint_spectrum
    seen_thresholds = []

    def threshold_checking_fingerprint(psd_result, signal_threshold_db=None, trace_key='psd_db'):
        seen_thresholds.append(signal_threshold_db)
        return real_fingerprint_spectrum(psd_result, signal_threshold_db=signal_threshold_db, trace_key=trace_key)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.fingerprint_spectrum", side_effect=threshold_checking_fingerprint),
        patch(
            "tools.capture_to_vectorstore.SignalClassifier.is_noise_shaped",
            return_value=False,
        ),
    ):
        run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=lambda _secs: None,
        )

    assert store.count() == 5
    assert all(t == expected_threshold for t in seen_thresholds)
    for meta in store._collection.get(include=["metadatas"])["metadatas"]:
        assert meta["signal_threshold_db"] == expected_threshold


def test_capture_targets_match_band_profiles():
    LABEL_TO_KEY = {
        "FM_broadcast": "fm_broadcast",
        "Aviation_VHF": "aviation",
        "ACARS": "acars",
        "APRS": "aprs",
        "AIS": "ais",
        "ISM_LoRa": "ism",
        "ADS_B": "adsb",
    }
    for target in CAPTURE_TARGETS:
        profile = BAND_PROFILES[LABEL_TO_KEY[target["label"]]]
        assert target["lna_gain_db"] == profile["lna_gain_db"]
        assert target["vga_gain_db"] == profile["vga_gain_db"]
        assert target["signal_threshold_db"] == profile["signal_threshold_db"]


def test_capture_targets_adsb_only_uses_max_hold():
    """Only the ADS_B target carries the psd_max_hold_db trace key."""
    for target in CAPTURE_TARGETS:
        if target["label"] == "ADS_B":
            assert target.get("trace_key") == "psd_max_hold_db"
        else:
            assert "trace_key" not in target


def test_trace_key_forwarded_to_fingerprint_spectrum(tmp_path: Path) -> None:
    """Forward ADS-B's max-hold trace key to the real fingerprint function.

    Mock the noise gate so the constant IQ fixture reaches storage while the
    fingerprint wrapper still records the trace_key argument passed by the loop.
    """
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    adsb_target = next(t for t in CAPTURE_TARGETS if t["label"] == "ADS_B")
    samples = np.ones(adsb_target["num_samples"], dtype=np.complex64)

    real_fingerprint_spectrum = capture_to_vectorstore.fingerprint_spectrum
    seen_trace_keys = []

    def trace_key_checking_fingerprint(psd_result, signal_threshold_db=None, trace_key='psd_db'):
        seen_trace_keys.append(trace_key)
        return real_fingerprint_spectrum(psd_result, signal_threshold_db=signal_threshold_db, trace_key=trace_key)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.fingerprint_spectrum", side_effect=trace_key_checking_fingerprint),
        patch(
            "tools.capture_to_vectorstore.SignalClassifier.is_noise_shaped",
            return_value=False,
        ),
    ):
        run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[adsb_target],
            antenna_name="Spiral discone",
            input_func=lambda _prompt: "",
            sleep_func=lambda _secs: None,
        )

    assert store.count() == 5
    assert all(t == "psd_max_hold_db" for t in seen_trace_keys)


def test_trace_key_defaults_to_psd_db_for_non_adsb(tmp_path: Path) -> None:
    """Forward the default psd_db trace key to the real fingerprint function.

    Mock the noise gate so the constant IQ fixture reaches storage while the
    fingerprint wrapper still records the trace_key argument passed by the loop.
    """
    store = SignalStore(str(tmp_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    fm_target = next(t for t in CAPTURE_TARGETS if t["label"] == "FM_broadcast")
    samples = np.ones(fm_target["num_samples"], dtype=np.complex64)

    real_fingerprint_spectrum = capture_to_vectorstore.fingerprint_spectrum
    seen_trace_keys = []

    def trace_key_checking_fingerprint(psd_result, signal_threshold_db=None, trace_key='psd_db'):
        seen_trace_keys.append(trace_key)
        return real_fingerprint_spectrum(psd_result, signal_threshold_db=signal_threshold_db, trace_key=trace_key)

    with (
        patch("tools.capture_to_vectorstore.capture_iq", return_value=samples),
        patch("tools.capture_to_vectorstore.fingerprint_spectrum", side_effect=trace_key_checking_fingerprint),
        patch(
            "tools.capture_to_vectorstore.SignalClassifier.is_noise_shaped",
            return_value=False,
        ),
    ):
        run_capture_loop(
            store=store,
            embedder=embedder,
            selected_targets=[fm_target],
            antenna_name="Telescopic whip",
            input_func=lambda _prompt: "",
            sleep_func=lambda _secs: None,
        )

    assert store.count() == 5
    assert all(t == "psd_db" for t in seen_trace_keys)


@pytest.mark.parametrize("occupied_bins", [0, 1])
def test_noise_shaped_captures_are_skipped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    occupied_bins: int,
) -> None:
    """Skip noise with concise output and keep normal capture waits."""
    store = SignalStore(str(tmp_path))
    target = dict(next(
        t for t in CAPTURE_TARGETS if t["label"] == "FM_broadcast"
    ))
    target.update(captures=3, num_samples=8)
    embedder = MagicMock(spec=capture_to_vectorstore.SpectrumEmbedder)
    with (
        patch(
            "tools.capture_to_vectorstore.capture_iq", return_value=np.ones(8),
        ),
        patch("tools.capture_to_vectorstore.compute_psd", return_value={}),
        patch(
            "tools.capture_to_vectorstore.fingerprint_spectrum", return_value={
                "occupied_bins": occupied_bins, "spectral_flatness": 0.95,
            },
        ),
        patch("tools.capture_to_vectorstore.build_metadata") as metadata,
        patch(
            "tools.capture_to_vectorstore.SignalClassifier",
            wraps=capture_to_vectorstore.SignalClassifier,
        ) as classifier,
    ):
        sleep = MagicMock()
        captured = run_capture_loop(
            store, embedder, [target], "Test antenna",
            input_func=lambda _prompt: "", sleep_func=sleep,
        )

    assert captured == 0
    assert store.count() == 0
    embedder.embed.assert_not_called()
    metadata.assert_not_called()
    classifier.assert_called_once_with()
    assert sleep.call_args_list == [call(5), call(5)]
    output = capsys.readouterr().out
    assert output.count("skipped: looks like noise") == 3
    assert "occupied_bins=" not in output
    assert "spectral_flatness=" not in output


@pytest.mark.parametrize(
    ("occupied_bins", "flatness"), [(2, 0.95), (1, 0.8999)],
)
def test_non_noise_fingerprint_is_stored(
    tmp_path: Path, occupied_bins: int, flatness: float,
) -> None:
    """Store fingerprints that fail either of the two noise conditions."""
    store = SignalStore(str(tmp_path))
    target = dict(next(
        t for t in CAPTURE_TARGETS if t["label"] == "FM_broadcast"
    ))
    target.update(captures=1, num_samples=8)
    fingerprint = {
        "peak_freq_hz": target["freq_hz"], "peak_power_db": -30.0,
        "noise_floor_db": -50.0, "snr_db": 20.0, "bandwidth_hz": 2000.0,
        "occupied_bins": occupied_bins, "spectral_flatness": flatness,
        "snr_margin_db": 2.0,
    }
    with (
        patch(
            "tools.capture_to_vectorstore.capture_iq", return_value=np.ones(8),
        ),
        patch("tools.capture_to_vectorstore.compute_psd", return_value={}),
        patch(
            "tools.capture_to_vectorstore.fingerprint_spectrum",
            return_value=fingerprint,
        ),
    ):
        captured = run_capture_loop(
            store, capture_to_vectorstore.SpectrumEmbedder(), [target],
            "Test antenna", input_func=lambda _prompt: "",
            sleep_func=lambda _seconds: None,
        )

    assert captured == 1
    assert store.count() == 1
    metadata = store.get_all_embeddings()["metadatas"][0]
    assert metadata["label"] == target["label"]


@pytest.fixture
def console_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> dict:
    """Exercise the real console workflow with fake RF and a temporary store.

    Keep storage and embedding real, seed one record, shorten each band to
    two captures and replace every wait and hardware entry point. Choose the
    discone using the appropriate displayed number for each device.
    """
    targets = [dict(t, captures=2, num_samples=8) for t in CAPTURE_TARGETS]
    fingerprint = {
        "peak_freq_hz": targets[0]["freq_hz"], "peak_power_db": -30.0,
        "noise_floor_db": -50.0, "snr_db": 20.0, "bandwidth_hz": 2000.0,
        "occupied_bins": 4, "spectral_flatness": 0.5, "snr_margin_db": 2.0,
    }
    store_path = tmp_path / "store"
    store = SignalStore(str(store_path))
    embedder = capture_to_vectorstore.SpectrumEmbedder()
    store.add({
        "id": "prior", "embedding": embedder.embed(fingerprint),
        "metadata": build_metadata(
            "FM_broadcast", "Test", targets[0], fingerprint, 0,
        ),
    })
    args = argparse.Namespace(
        wipe=False, device="hackrf", band=None, freq_mhz=None,
        captures=None, verbose=False,
    )
    capture = MagicMock(return_value=np.ones(8, dtype=np.complex64))
    pluto_capture = MagicMock(return_value=np.ones(8, dtype=np.complex64))
    fingerprint_mock = MagicMock(return_value=fingerprint)
    prompt = MagicMock(
        side_effect=lambda _prompt: "2" if args.device == "pluto" else "3",
    )
    sleep = MagicMock()
    soapy = ModuleType("SoapySDR")
    soapy.SOAPY_SDR_WARNING = 4
    soapy.SoapySDR_setLogLevel = MagicMock()
    monkeypatch.setitem(sys.modules, "SoapySDR", soapy)
    monkeypatch.setattr(capture_to_vectorstore, "CAPTURE_TARGETS", targets)
    monkeypatch.setattr(capture_to_vectorstore, "_parse_args", lambda: args)
    monkeypatch.setattr(
        capture_to_vectorstore, "Path", lambda _path: store_path,
    )
    monkeypatch.setattr(capture_to_vectorstore, "capture_iq", capture)
    monkeypatch.setattr(
        capture_to_vectorstore, "capture_iq_pluto", pluto_capture,
    )
    monkeypatch.setattr(
        capture_to_vectorstore, "compute_psd", MagicMock(return_value={}),
    )
    monkeypatch.setattr(
        capture_to_vectorstore, "fingerprint_spectrum", fingerprint_mock,
    )
    monkeypatch.setattr("builtins.input", prompt)
    monkeypatch.setattr(
        capture_to_vectorstore, "run_capture_loop",
        partial(run_capture_loop, sleep_func=sleep),
    )
    return {
        "args": args, "store": store, "embedder": embedder,
        "targets": targets, "fingerprint": fingerprint,
        "fingerprint_mock": fingerprint_mock, "capture": capture,
        "pluto_capture": pluto_capture, "prompt": prompt,
        "sleep": sleep, "soapy": soapy,
    }


def test_one_prompt_per_band(console_capture: dict) -> None:
    """Prompt once for every band, including bands without traffic warnings."""
    prompt = MagicMock(return_value="")
    count = run_capture_loop(
        console_capture["store"], console_capture["embedder"],
        console_capture["targets"], "Telescopic whip",
        input_func=prompt, sleep_func=console_capture["sleep"],
    )
    assert prompt.call_count == len(CAPTURE_TARGETS)
    assert all(
        "Enter to start · Ctrl+C to skip this band" in args[0]
        for args, _kwargs in prompt.call_args_list
    )
    assert count == 2 * len(CAPTURE_TARGETS)


@pytest.mark.parametrize(
    ("label", "expected"), [
        ("ADS_B", [
            "Retract it to ~68 mm before you start",
            "flightradar24.com", "Aircraft overhead",
        ]),
        ("ACARS", ["flightradar24.com", "Active aircraft traffic"]),
        ("AIS", ["marinetraffic.com", "Vessels within range"]),
        ("FM_broadcast", []),
    ],
)
def test_band_card_content(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
    label: str, expected: list[str],
) -> None:
    """Show antenna instructions, gain and applicable live-traffic advice."""
    target = next(t for t in console_capture["targets"] if t["label"] == label)
    run_capture_loop(
        console_capture["store"], console_capture["embedder"], [target],
        "Telescopic whip", input_func=lambda _prompt: "",
        sleep_func=console_capture["sleep"],
    )
    output = capsys.readouterr().out
    assert f"[1/1] {label} · {target['freq_hz'] / 1e6:.3f} MHz" in output
    assert "Antenna" in output
    assert (
        f"LNA {target['lna_gain_db']} dB, VGA {target['vga_gain_db']} dB"
    ) in output
    assert f"threshold {target['signal_threshold_db']:.1f} dB" in output
    for text in expected:
        assert text in output
    if label == "FM_broadcast":
        assert "Signal" not in output
        assert "Live traffic:" not in output


def test_band_summary_with_noise_and_snr(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
) -> None:
    """Summarise stored and noise counts and the accepted SNR range."""
    target = dict(console_capture["targets"][0], captures=3)
    fingerprint = console_capture["fingerprint"]
    console_capture["fingerprint_mock"].side_effect = [
        dict(fingerprint, snr_db=12.1),
        dict(fingerprint, occupied_bins=1, spectral_flatness=0.95),
        dict(fingerprint, snr_db=16.4),
    ]
    results = []
    count = run_capture_loop(
        console_capture["store"], console_capture["embedder"], [target],
        "Test antenna", input_func=lambda _prompt: "",
        sleep_func=console_capture["sleep"], results=results,
    )
    assert count == 2
    assert results == [{
        "label": target["label"], "stored": 2, "noise": 1,
        "failed": False, "skipped": False,
    }]
    assert (
        "✓ 2/3 stored · 1 skipped as noise · SNR 12.1 to 16.4 dB"
    ) in capsys.readouterr().out


@pytest.mark.parametrize("verbose", [False, True])
def test_console_logging_and_plain_output(
    console_capture: dict, capsys: pytest.CaptureFixture[str], verbose: bool,
) -> None:
    """Keep pipes plain and enable only Mimir INFO in verbose mode."""
    console_capture["args"].verbose = verbose
    original = console_capture["fingerprint"]

    def fingerprint_with_logs(*_args: object, **_kwargs: object) -> dict:
        """Emit Mimir and explicitly enabled library INFO during capture."""
        logging.getLogger("chromadb").setLevel(logging.INFO)
        logging.getLogger("chromadb").info("hidden library detail")
        logging.getLogger("core").info("Mimir capture detail")
        return original

    console_capture["fingerprint_mock"].side_effect = fingerprint_with_logs
    capture_to_vectorstore.main()
    output = capsys.readouterr()
    assert (
        "✓ capture 1/2 stored · peak -30.00 dB · SNR 20.00 dB · margin 2.00 dB"
    ) in output.out
    assert ("Mimir capture detail" in output.err) == verbose
    assert "hidden library detail" not in output.out + output.err
    assert "\x1b[" not in output.out + output.err
    assert "\r" not in output.out + output.err
    assert logging.getLogger().level == logging.WARNING
    if not verbose:
        assert output.err == ""


class CaptureTTY(io.StringIO):
    """Represent a colour-capable terminal without any hardware access."""

    def isatty(self) -> bool:
        """Enable the shared console helper's TTY behaviour."""
        return True


@pytest.mark.parametrize("verbose", [False, True])
def test_tty_capture_details_and_colour(
    console_capture: dict, monkeypatch: pytest.MonkeyPatch, verbose: bool,
) -> None:
    """Colour TTY output and limit per-capture detail to verbose mode."""
    stream = CaptureTTY()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", stream)
    console_capture["args"].verbose = verbose
    capture_to_vectorstore.main()
    output = stream.getvalue()
    assert "\x1b[" in output
    assert ("capture 1/2 stored" in output) == verbose
    assert ("peak -30.00 dB" in output) == verbose
    assert "2/2 stored" in output


def test_verbose_noise_measurements(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
) -> None:
    """Add occupied-bin and flatness detail only when verbose is requested."""
    console_capture["args"].verbose = True
    console_capture["fingerprint_mock"].return_value = {
        "occupied_bins": 1, "spectral_flatness": 0.95,
    }
    capture_to_vectorstore.main()
    output = capsys.readouterr()
    assert "occupied_bins=1, spectral_flatness=0.950000" in output.out
    assert "Skipped noise-shaped capture" in output.err


@pytest.mark.parametrize("device", ["hackrf", "pluto"])
@pytest.mark.parametrize("wipe", [False, True])
def test_no_new_captures_exits_with_recovery_advice(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
    device: str, wipe: bool,
) -> None:
    """Report total failure, prior-record state and device recovery advice."""
    console_capture["args"].device = device
    console_capture["args"].wipe = wipe
    capture = console_capture[
        "pluto_capture" if device == "pluto" else "capture"
    ]
    capture.side_effect = RuntimeError("receiver unavailable")
    with pytest.raises(SystemExit) as error:
        capture_to_vectorstore.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    box_text = " ".join(line.strip("│ ") for line in output.out.splitlines())
    assert "No new captures" in output.out
    assert "No band stored any capture." in output.out
    assert "Capture complete" not in output.out
    if wipe:
        assert "store was wiped at the start of this run" in output.out
        assert "earlier records are gone" in box_text
        assert "left unchanged" not in output.out
    else:
        assert "data/vectorstore was left unchanged" in output.out
        assert console_capture["store"].count() == 1
    device_name, command = (
        ("Pluto", "iio_info") if device == "pluto"
        else ("HackRF", "hackrf_info")
    )
    assert (
        f"→ Next: check the {device_name} is plugged in "
        f"({command} should list it), then run again"
    ) in output.out
    assert capture.call_count == 2
    assert output.out.count("receiver unavailable") == 2
    assert output.err == ""
    console_capture["sleep"].assert_not_called()
    console_capture["soapy"].SoapySDR_setLogLevel.assert_called_once_with(4)


@pytest.mark.parametrize(
    "outcome", ["noise", "skipped", "partial", "later_failure"],
)
def test_nonfatal_empty_and_partial_runs_complete(
    console_capture: dict, capsys: pytest.CaptureFixture[str], outcome: str,
) -> None:
    """Complete noise-only, all-skipped and partly successful runs normally."""
    if outcome == "noise":
        console_capture["fingerprint_mock"].return_value = {
            "occupied_bins": 1, "spectral_flatness": 0.95,
        }
    elif outcome == "skipped":
        console_capture["prompt"].side_effect = [
            "3", KeyboardInterrupt(), KeyboardInterrupt(),
        ]
    elif outcome == "partial":
        console_capture["capture"].side_effect = [
            RuntimeError("first band failed"), np.ones(8), np.ones(8),
        ]
    else:
        console_capture["capture"].side_effect = [
            np.ones(8), RuntimeError("later capture failed"),
            RuntimeError("next band failed"),
        ]
    capture_to_vectorstore.main()
    output = capsys.readouterr().out
    assert "Capture complete" in output
    assert "No new captures" not in output
    assert (
        "→ Next: ./mimir tool calibrate_thresholds --device hackrf"
    ) in output
    if outcome in ("noise", "skipped"):
        assert console_capture["store"].count() == 1
        assert "1 → 1 records" in output
        assert ("noise" if outcome == "noise" else "skipped") in output
    else:
        assert "failed" in output
        assert console_capture["store"].count() == (
            3 if outcome == "partial" else 2
        )
    if outcome == "skipped":
        console_capture["capture"].assert_not_called()


@pytest.mark.parametrize("device", ["hackrf", "pluto"])
def test_capture_complete_header_and_counts(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch, device: str,
) -> None:
    """Check header continuation alignment, counts and calibration command."""
    monkeypatch.setattr(
        _console.shutil, "get_terminal_size",
        MagicMock(return_value=argparse.Namespace(columns=80)),
    )
    console_capture["args"].device = device
    capture_to_vectorstore.main()
    output = capsys.readouterr().out
    # Check the header separately so card antenna rows cannot hide a repeat.
    header = output.split("╭─ Mimir", 1)[1].split("╰", 1)[0]
    assert "Antenna" not in header
    header_rows = [line for line in header.splitlines() if line.startswith("│")]
    skipped_row = next(line for line in header_rows if "Skipped" in line)
    reason_row = header_rows[header_rows.index(skipped_row) + 1]
    value_column = 3 + len("Skipped") + 3
    assert reason_row.index("(") == value_column
    assert skipped_row[value_column] != " "
    assert reason_row[3:reason_row.index("(")].isspace()
    assert all(len(line) == 72 for line in header_rows)
    box_body = " ".join(
        line.strip("│ ") for line in header_rows
    )
    assert f"Mimir · capture to vectorstore · {device}" in output
    assert "ISM_LoRa, ADS_B" in output
    assert "1 records in data/vectorstore" in output
    assert "Capture complete" in output
    assert "1 → 5 records" in output
    assert (
        f"→ Next: ./mimir tool calibrate_thresholds --device {device}"
    ) in output
    if device == "pluto":
        assert "outside Pluto's range" in box_body
        assert "gain " in output
        assert "LNA " not in output
        console_capture["capture"].assert_not_called()
    else:
        assert "outside this antenna's range" in box_body
        console_capture["pluto_capture"].assert_not_called()


@pytest.mark.parametrize(
    ("options", "message"), [
        ({"band": "adsb", "captures": 0},
         "--captures must be a positive integer"),
        ({"freq_mhz": 1090.0}, "--freq-mhz and --captures require --band"),
        ({"captures": 2}, "--freq-mhz and --captures require --band"),
        ({"band": "fm_broadcast"}, "--band fm_broadcast is not reachable"),
    ],
)
def test_setup_error_box(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
    options: dict, message: str,
) -> None:
    """Render invalid overrides as a failure box and exit before capturing."""
    for name, value in options.items():
        setattr(console_capture["args"], name, value)
    with pytest.raises(SystemExit) as error:
        capture_to_vectorstore.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "╭─ Setup error" in output
    assert message in output
    console_capture["capture"].assert_not_called()
    assert console_capture["store"].count() == 1


def test_header_uses_validated_overrides(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
) -> None:
    """Show the final band and override notes after antenna selection."""
    args = console_capture["args"]
    args.band, args.freq_mhz, args.captures = "adsb", 1090.0, 1
    capture_to_vectorstore.main()
    output = capsys.readouterr().out
    header = output[output.index("╭─ Mimir"):output.index("╭─ [1/1]")]
    assert "Bands" in header and "ADS_B" in header
    assert "ISM_LoRa, ADS_B" not in header
    assert "--band filter applied" in header
    assert "--freq-mhz override" in header
    assert "--captures override" in header
    assert "calibrated for the default frequency" in " ".join(
        line.strip("│ ") for line in header.splitlines()
    )
    assert console_capture["capture"].call_count == 1


@pytest.mark.parametrize(
    "setter_name", ["SoapySDR_setLogLevel", "setLogLevel"],
)
def test_quiet_soapy_info_logs(
    monkeypatch: pytest.MonkeyPatch, setter_name: str,
) -> None:
    """Set only the warning log level through either supported fake binding."""
    soapy = ModuleType("SoapySDR")
    setter = MagicMock()
    setattr(soapy, setter_name, setter)
    soapy.SOAPY_SDR_WARNING = 4
    monkeypatch.setitem(sys.modules, "SoapySDR", soapy)
    capture_to_vectorstore._quiet_soapy_info_logs()
    setter.assert_called_once_with(4)


@pytest.mark.parametrize("missing", ["module", "setter", "level"])
def test_quiet_soapy_missing_controls(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    missing: str,
) -> None:
    """Log at DEBUG and carry on when bindings or log controls are absent."""
    soapy = ModuleType("SoapySDR")
    setter = MagicMock()
    if missing != "setter":
        soapy.setLogLevel = setter
    if missing != "level":
        soapy.SOAPY_SDR_WARNING = 4
    monkeypatch.setitem(
        sys.modules, "SoapySDR", None if missing == "module" else soapy,
    )
    with caplog.at_level(
        logging.DEBUG, logger=capture_to_vectorstore.__name__,
    ):
        capture_to_vectorstore._quiet_soapy_info_logs()
    setter.assert_not_called()
    assert "leaving" in caplog.text


@pytest.mark.parametrize("verbose", [False, True])
def test_parse_verbose_flag(
    monkeypatch: pytest.MonkeyPatch, verbose: bool,
) -> None:
    """Default to quiet logs and enable details with the explicit CLI flag."""
    monkeypatch.setattr(
        sys, "argv", ["capture_to_vectorstore"]
        + (["--verbose"] if verbose else []),
    )
    assert capture_to_vectorstore._parse_args().verbose == verbose


def test_default_logging_hides_warnings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Suppress default WARNING and INFO records with a null handler."""
    capture_to_vectorstore._configure_console_logging(False)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.NullHandler)
    logging.getLogger("core").warning("hidden Mimir warning")
    logging.getLogger("chromadb").warning("hidden library warning")
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize(
    "error", [
        KeyboardInterrupt(), SystemExit(2), ValueError("processing error"),
    ],
)
def test_spinner_clears_on_interrupted_capture(
    console_capture: dict, error: BaseException,
) -> None:
    """Keep prompts outside progress and unregister it on raised errors."""
    console_capture["capture"].side_effect = error

    def prompt_without_spinner(_prompt: str) -> str:
        """Verify no progress is registered while asking for band readiness."""
        assert _console._current_spinner is None
        return ""

    with pytest.raises(type(error)):
        run_capture_loop(
            console_capture["store"], console_capture["embedder"],
            [console_capture["targets"][0]], "Test antenna",
            input_func=prompt_without_spinner,
            sleep_func=console_capture["sleep"],
        )
    assert _console._current_spinner is None


def test_wiped_header_uses_empty_store_count(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
) -> None:
    """Display post-wipe record counts in both the header and final summary."""
    console_capture["args"].wipe = True
    capture_to_vectorstore.main()
    output = capsys.readouterr().out
    assert "╭─ Wipe vector store" in output
    assert "Vector store wiped and reinitialised." in output
    assert "0 records in data/vectorstore" in output
    assert "0 → 4 records" in output


@pytest.mark.parametrize(
    "problem", ["missing_profiles", "unsupported", "missing_gain"],
)
def test_pluto_setup_errors_render_boxes(
    console_capture: dict, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], problem: str,
) -> None:
    """Box each Pluto configuration error without opening a device."""
    from dashboard import shared_state

    console_capture["args"].device = "pluto"
    if problem == "missing_profiles":
        monkeypatch.delattr(shared_state, "PLUTO_BAND_PROFILES")
        expected = "PLUTO_BAND_PROFILES does not exist yet"
    elif problem == "unsupported":
        monkeypatch.setattr(
            shared_state, "band_supported_by_device",
            lambda _key, _device: False,
        )
        monkeypatch.setattr(
            shared_state, "PLUTO_BAND_PROFILES",
            {"ism": {"reason": "uncalibrated test band"}},
        )
        expected = "Pluto does not support 'ism'"
    else:
        monkeypatch.setattr(
            shared_state, "band_supported_by_device",
            lambda _key, _device: True,
        )
        monkeypatch.setattr(
            shared_state, "PLUTO_BAND_PROFILES", {"ism": {}},
        )
        expected = "missing 'gain_db' or 'signal_threshold_db'"
    with pytest.raises(SystemExit) as error:
        capture_to_vectorstore.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    text = " ".join(line.strip("│ ") for line in output.splitlines())
    assert "╭─ Setup error" in output
    assert expected in text
    console_capture["capture"].assert_not_called()
    console_capture["pluto_capture"].assert_not_called()


@pytest.mark.parametrize(
    ("choice", "antenna_name"), [
        ("1", "Telescopic whip"), ("2", "Spiral discone"),
    ],
)
def test_pluto_antenna_choices_apply_to_both_bands(
    console_capture: dict, capsys: pytest.CaptureFixture[str],
    choice: str, antenna_name: str,
) -> None:
    """Use the real antenna name for both bands from either Pluto choice."""
    console_capture["args"].device = "pluto"
    console_capture["prompt"].side_effect = [choice, "", ""]
    with patch.object(
        capture_to_vectorstore, "run_capture_loop",
        wraps=capture_to_vectorstore.run_capture_loop,
    ) as loop:
        capture_to_vectorstore.main()
    assert loop.call_args.kwargs["antenna_name"] == antenna_name
    metadatas = console_capture["store"].get_all_embeddings()["metadatas"]
    live = [
        metadata for metadata in metadatas
        if metadata["label"] != "FM_broadcast"
    ]
    assert len(live) == 4
    assert {metadata["antenna"] for metadata in live} == {antenna_name}
    assert {metadata["label"] for metadata in live} == {"ISM_LoRa", "ADS_B"}
    console_capture["capture"].assert_not_called()
    output = capsys.readouterr().out
    assert (
        "Which antenna is on the Pluto? Both bands are captured with it."
    ) in output
    assert "1   Telescopic whip   best for ADS_B" in output
    assert "2   Spiral discone    best for ISM_LoRa" in output
    assert "V-dipole" not in output
    assert console_capture["prompt"].call_args_list[0] == call(
        "  Choose 1 or 2 (Ctrl+C to cancel): "
    )


@pytest.mark.parametrize("invalid", ["3", "", "whip"])
def test_pluto_antenna_invalid_input_reasks(
    console_capture: dict, capsys: pytest.CaptureFixture[str], invalid: str,
) -> None:
    """Reject old profile number 3 and other invalid Pluto menu input."""
    console_capture["args"].device = "pluto"
    console_capture["prompt"].side_effect = [invalid, "2", "", ""]
    capture_to_vectorstore.main()
    assert console_capture["prompt"].call_args_list[:2] == [
        call("  Choose 1 or 2 (Ctrl+C to cancel): "),
        call("  Choose 1 or 2 (Ctrl+C to cancel): "),
    ]
    assert capsys.readouterr().out.count("Please choose 1 or 2.") == 1
    assert console_capture["pluto_capture"].call_count == 4


def test_pluto_antenna_interrupt_cancels(console_capture: dict) -> None:
    """Cancel Pluto selection with exit 0 before attempting a capture."""
    console_capture["args"].device = "pluto"
    console_capture["prompt"].side_effect = KeyboardInterrupt
    with (
        patch.object(capture_to_vectorstore.logger, "info") as log,
        pytest.raises(SystemExit) as error,
    ):
        capture_to_vectorstore.main()
    assert error.value.code == 0
    log.assert_any_call("User aborted Pluto capture at antenna selection")
    console_capture["capture"].assert_not_called()
    console_capture["pluto_capture"].assert_not_called()
    assert console_capture["store"].count() == 1


@pytest.mark.parametrize("choice", ["1", "2", "3"])
def test_hackrf_antenna_wording_and_reask(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    choice: str,
) -> None:
    """Explain HackRF antenna selection for the run and re-ask invalid input."""
    prompt = MagicMock(side_effect=["invalid", choice])
    monkeypatch.setattr("builtins.input", prompt)
    key, profile = capture_to_vectorstore._select_antenna()
    assert key == choice
    assert profile is ANTENNA_PROFILES[choice]
    assert prompt.call_args_list == [
        call("  Choose 1, 2 or 3 (Ctrl+C to cancel): "),
        call("  Choose 1, 2 or 3 (Ctrl+C to cancel): "),
    ]
    output = capsys.readouterr().out
    assert (
        "Which antenna is on the HackRF? "
        "Every band it covers is captured with it."
    ) in output
    assert output.count("Please choose 1, 2 or 3.") == 1


def test_hackrf_antenna_interrupt_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep HackRF cancellation at exit 0 with its existing log record."""
    monkeypatch.setattr(
        "builtins.input", MagicMock(side_effect=KeyboardInterrupt),
    )
    with (
        patch.object(capture_to_vectorstore.logger, "info") as log,
        pytest.raises(SystemExit) as error,
    ):
        capture_to_vectorstore._select_antenna()
    assert error.value.code == 0
    log.assert_called_once_with("User aborted capture at antenna selection")


@pytest.mark.parametrize(
    ("label", "antenna_name", "hint"), [
        ("ISM_LoRa", "Telescopic whip",
         "⚠ Spiral discone works better for this band"),
        ("ISM_LoRa", "Spiral discone", ""),
        ("ADS_B", "Telescopic whip",
         "Retract it to ~68 mm before you start"),
        ("ADS_B", "Spiral discone",
         "⚠ Telescopic whip (retracted to ~68 mm) works better for this band"),
        ("FM_broadcast", "Telescopic whip", ""),
    ],
)
def test_band_antenna_hints_are_aligned_plain_advice(
    console_capture: dict, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str, antenna_name: str, hint: str,
) -> None:
    """Align plain hints under the real antenna and let Enter capture."""
    monkeypatch.setenv("NO_COLOR", "1")
    target = next(t for t in console_capture["targets"] if t["label"] == label)
    prompt = MagicMock(return_value="")
    with patch.object(
        capture_to_vectorstore, "box", wraps=_console.box,
    ) as box:
        count = run_capture_loop(
            console_capture["store"], console_capture["embedder"], [target],
            antenna_name, input_func=prompt,
            sleep_func=console_capture["sleep"],
        )
    assert count == 2
    prompt.assert_called_once()
    rows = box.call_args.args[1]
    assert rows[0] == f"{'Antenna':8}   {antenna_name}"
    # The Captures key fixes the value column at 11, even on continued hints.
    hint_rows = []
    for row in rows[1:]:
        if row.startswith("Signal") or row.startswith("Captures"):
            break
        hint_rows.append(row)
    assert " ".join(row.strip() for row in hint_rows) == hint
    assert all(row.startswith(" " * 11) for row in hint_rows)
    assert all(len(row) <= 66 for row in rows)
    output = capsys.readouterr().out
    assert "\x1b[" not in output
    assert ", retracted to ~68 mm" not in output
    stored = console_capture["store"].get_all_embeddings()["metadatas"]
    assert all(
        metadata["antenna"] == antenna_name
        for metadata in stored if metadata["label"] == label
        and metadata["antenna"] != "Test"
    )


@pytest.mark.parametrize(
    ("device", "profile_key"), [
        ("hackrf", "1"), ("hackrf", "2"), ("hackrf", "3"),
        ("pluto", "1"), ("pluto", "3"),
    ],
)
def test_header_and_card_rows_fit_standard_box(
    console_capture: dict, monkeypatch: pytest.MonkeyPatch,
    device: str, profile_key: str,
) -> None:
    """Keep every standard header/card row inside the 66-column box body."""
    console_capture["args"].device = device
    displayed_choice = (
        {"1": "1", "3": "2"}[profile_key]
        if device == "pluto" else profile_key
    )
    console_capture["prompt"].side_effect = None
    console_capture["prompt"].return_value = displayed_choice
    monkeypatch.setenv("NO_COLOR", "1")
    with patch.object(
        capture_to_vectorstore, "box", wraps=_console.box,
    ) as box:
        capture_to_vectorstore.main()
    for captured_call in box.call_args_list:
        title, rows = captured_call.args[:2]
        if title.startswith("Mimir") or title.startswith("["):
            assert all(_console.visible_len(row) <= 66 for row in rows)
