"""
tools/compare_decode_rate.py
Mimir RF Scanner — HackRF vs ADALM-PLUTO ADS-B Decode-Rate Comparison

LEGAL NOTICE
────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

This tool is RECEIVE-ONLY. It opens each SDR through Mimir's own receive-only
wrapper and touches only the receive interface (open / tune / read_samples /
close). No transmit method is ever called. Both wrappers raise
HardwareTransmitError on any TX call regardless.

WHAT THIS TOOL DOES
───────────────────
Answers one narrow question that three prior threshold-based A/B attempts could
not settle: given the same antenna and the same sky, which device delivers more
VALID ADS-B frames to pyModeS?

It deliberately avoids PSD thresholds, SNR, kurtosis, or any interpretation. It
runs each device's raw IQ through Mimir's real production decode path
(AdsbDemodulator → AdsbDecoder) and counts how many frames come back as a
CRC-valid DF17/18 extended squitter with a valid ICAO — i.e. a real decode.

WHY THIS IS A FAIR COMPARISON
─────────────────────────────
- Both devices run for the SAME wall-clock duration at the SAME 2 MHz sample
  rate, so both process the same amount of RF time.
- Frame count is an END-TO-END outcome. The two devices have different gain
  architectures (HackRF: split LNA+VGA; Pluto: single combined stage), and no
  dB value is equivalent across them. So each device is run at its OWN
  production ADS-B gain — "each device as Mimir would actually run it" — which
  is the decision this test exists to inform. Override with --hackrf-gain /
  --pluto-gain if you want a sweep.
- The demodulator is stateless per chunk, so a small number of frames straddling
  chunk boundaries are lost — equally for both devices, so it does not bias the
  comparison.

HOW TO RUN
──────────
    PYTHONPATH=. python tools/compare_decode_rate.py

    # shorter smoke run (2 minutes per device):
    PYTHONPATH=. python tools/compare_decode_rate.py --duration 120

    # override gains for a sweep point:
    PYTHONPATH=. python tools/compare_decode_rate.py --pluto-gain 35

PYTHONPATH=. is required — Mimir is not an installed package, so Python needs
the repo root on its import path to find core/ and modules/.

Only one device is open at a time. The tool captures HackRF first, then pauses
and prompts you to physically unplug it and plug in the Pluto before continuing.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field

import numpy as np

from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver
from modules.adsb.constants import AU_ADSB_FREQUENCY_HZ
from modules.adsb.decoder import AdsbDecoder
from modules.adsb.demodulator import AdsbDemodulator

logger = logging.getLogger("compare_decode_rate")

# Capture parameters shared by BOTH devices — identical by design so the only
# variable between the two runs is the hardware itself.
SAMPLE_RATE_HZ: float = 2_000_000
SAMPLES_PER_READ: int = 2_000_000  # ~1.0 s of RF per iteration at 2 MHz
DEFAULT_DURATION_SEC: float = 600.0  # 10 minutes per device
PROGRESS_INTERVAL_SEC: float = 30.0

# Each device's production ADS-B gain (see module docstring for why these, not
# a single "matched" value).
HACKRF_ADSB_LNA_DB: float = 24.0
HACKRF_ADSB_VGA_DB: float = 24.0
PLUTO_ADSB_GAIN_DB: float = 30.0


@dataclass
class DecodeStats:
    """Running totals for a single device's capture run."""

    device_name: str
    valid_frames: int = 0
    chunks_processed: int = 0
    samples_processed: int = 0
    elapsed_sec: float = 0.0
    icaos: set[str] = field(default_factory=set)

    @property
    def frames_per_min(self) -> float:
        if self.elapsed_sec <= 0:
            return 0.0
        return self.valid_frames / (self.elapsed_sec / 60.0)

    @property
    def unique_aircraft(self) -> int:
        return len(self.icaos)


def _run_capture(
    device,
    device_name: str,
    duration_sec: float,
) -> DecodeStats:
    """Capture from an already-configured device and count valid ADS-B frames.

    The device must already be open and tuned. This function only reads samples
    and feeds them through the production decode path — it never changes tuning
    or gain, and never touches any transmit interface.

    Args:
        device: An open HackRFReceiver or PlutoReceiver (RX-only wrapper).
        device_name: Human-readable label for logging and the summary.
        duration_sec: Wall-clock seconds to capture for.

    Returns:
        A populated DecodeStats.
    """
    demodulator = AdsbDemodulator()
    decoder = AdsbDecoder()
    stats = DecodeStats(device_name=device_name)

    start = time.monotonic()
    next_progress = start + PROGRESS_INTERVAL_SEC
    deadline = start + duration_sec

    logger.info(
        "%s: capturing %.0f s at %.3f MHz, %.1f MHz sample rate...",
        device_name,
        duration_sec,
        AU_ADSB_FREQUENCY_HZ / 1e6,
        SAMPLE_RATE_HZ / 1e6,
    )

    try:
        while time.monotonic() < deadline:
            iq_chunk = device.read_samples(SAMPLES_PER_READ)
            stats.chunks_processed += 1
            stats.samples_processed += int(iq_chunk.shape[0])

            for raw_hex in demodulator.demodulate(iq_chunk):
                msg = decoder.decode(raw_hex)
                if msg is not None:
                    stats.valid_frames += 1
                    if msg.icao:
                        stats.icaos.add(msg.icao)

            now = time.monotonic()
            if now >= next_progress:
                elapsed = now - start
                logger.info(
                    "%s: %5d frames | %3d aircraft | %.0f s elapsed",
                    device_name,
                    stats.valid_frames,
                    stats.unique_aircraft,
                    elapsed,
                )
                next_progress = now + PROGRESS_INTERVAL_SEC
    except KeyboardInterrupt:
        logger.warning(
            "%s: interrupted by Ctrl-C — ending this device's run early.",
            device_name,
        )

    stats.elapsed_sec = time.monotonic() - start
    return stats


def _capture_hackrf(duration_sec: float, lna_db: float, vga_db: float) -> DecodeStats:
    """Open the HackRF, capture, and guarantee close() even on failure."""
    device = HackRFReceiver(
        center_freq_hz=AU_ADSB_FREQUENCY_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        lna_gain_db=lna_db,
        vga_gain_db=vga_db,
        amp_enable=False,
    )
    device.open()
    try:
        logger.info(
            "HackRF One open at ADS-B gain LNA=%.0f / VGA=%.0f dB, AMP off.",
            lna_db,
            vga_db,
        )
        return _run_capture(device, "HackRF One", duration_sec)
    finally:
        device.close()


def _capture_pluto(duration_sec: float, gain_db: float) -> DecodeStats:
    """Open the Pluto, capture, and guarantee close() even on failure."""
    device = PlutoReceiver(
        center_freq_hz=AU_ADSB_FREQUENCY_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        gain_db=gain_db,
    )
    device.open()
    try:
        logger.info("ADALM-PLUTO open at ADS-B gain %.1f dB (combined).", gain_db)
        return _run_capture(device, "ADALM-PLUTO", duration_sec)
    finally:
        device.close()


def _print_summary(hackrf: DecodeStats, pluto: DecodeStats) -> None:
    """Print the side-by-side comparison and a plain-language verdict."""
    line = "=" * 66
    print(f"\n{line}")
    print("  ADS-B DECODE-RATE COMPARISON — valid pyModeS frames")
    print(f"{line}")
    header = f"  {'Metric':<26}{'HackRF One':>18}{'ADALM-PLUTO':>18}"
    print(header)
    print(f"  {'-' * 62}")

    def row(label: str, a: str, b: str) -> None:
        print(f"  {label:<26}{a:>18}{b:>18}")

    row("Valid frames", str(hackrf.valid_frames), str(pluto.valid_frames))
    row(
        "Frames / minute",
        f"{hackrf.frames_per_min:.1f}",
        f"{pluto.frames_per_min:.1f}",
    )
    row("Unique aircraft", str(hackrf.unique_aircraft), str(pluto.unique_aircraft))
    row("Elapsed (s)", f"{hackrf.elapsed_sec:.0f}", f"{pluto.elapsed_sec:.0f}")
    row("Chunks processed", str(hackrf.chunks_processed), str(pluto.chunks_processed))
    print(f"{line}")

    # Verdict — normalise by frames/min in case the two runs differ in length
    # (e.g. one was cut short with Ctrl-C).
    h_rate = hackrf.frames_per_min
    p_rate = pluto.frames_per_min
    if h_rate == 0 and p_rate == 0:
        print("  No valid frames on either device. Check antenna, sky, and gain.")
    elif p_rate == 0:
        print("  Only the HackRF decoded frames in this run.")
    elif h_rate == 0:
        print("  Only the Pluto decoded frames in this run.")
    else:
        better, worse, ratio = (
            ("HackRF One", "Pluto", h_rate / p_rate)
            if h_rate >= p_rate
            else ("ADALM-PLUTO", "HackRF", p_rate / h_rate)
        )
        print(
            f"  {better} decoded {ratio:.2f}x the frames/min of the {worse} "
            f"in this run."
        )
    print(f"{line}")
    print(
        "  Note: one run is a single sample under one set of sky conditions. "
        "Re-run at\n  a different time, or add gain sweep points, before "
        "treating this as settled."
    )
    print(f"{line}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare HackRF vs ADALM-PLUTO by counting valid ADS-B frames "
            "decoded through Mimir's real pyModeS path. Receive-only."
        )
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SEC,
        help=f"Seconds to capture per device (default: {DEFAULT_DURATION_SEC:.0f}).",
    )
    parser.add_argument(
        "--hackrf-lna",
        type=float,
        default=HACKRF_ADSB_LNA_DB,
        help=f"HackRF LNA gain dB (default: {HACKRF_ADSB_LNA_DB:.0f}).",
    )
    parser.add_argument(
        "--hackrf-vga",
        type=float,
        default=HACKRF_ADSB_VGA_DB,
        help=f"HackRF VGA gain dB (default: {HACKRF_ADSB_VGA_DB:.0f}).",
    )
    parser.add_argument(
        "--pluto-gain",
        type=float,
        default=PLUTO_ADSB_GAIN_DB,
        help=f"Pluto combined gain dB (default: {PLUTO_ADSB_GAIN_DB:.0f}).",
    )
    parser.add_argument(
        "--skip-pluto",
        action="store_true",
        help="Capture the HackRF only and exit (no replug prompt).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print(
        "\nADS-B decode-rate comparison — RECEIVE ONLY (AU/SA, "
        "Radiocommunications Act 1992).\n"
        f"Tuning both devices to {AU_ADSB_FREQUENCY_HZ / 1e6:.0f} MHz, "
        f"{args.duration:.0f} s each.\n"
        "Keep the same antenna on both devices for a fair comparison.\n"
    )

    input("Plug in the HackRF One (only), attach the antenna, then press Enter... ")

    try:
        hackrf_stats = _capture_hackrf(
            args.duration, args.hackrf_lna, args.hackrf_vga
        )
    except (RuntimeError, OSError) as exc:
        logger.error("HackRF capture failed: %s", exc)
        return 1

    if args.skip_pluto:
        line = "=" * 66
        print(f"\n{line}")
        print(
            f"  HackRF One: {hackrf_stats.valid_frames} frames "
            f"({hackrf_stats.frames_per_min:.1f}/min), "
            f"{hackrf_stats.unique_aircraft} aircraft, "
            f"{hackrf_stats.elapsed_sec:.0f} s."
        )
        print(f"{line}\n")
        return 0

    print(
        "\n--- HackRF capture done. Now SWAP DEVICES: ---\n"
        "  1. Unplug the HackRF One.\n"
        "  2. Plug in the ADALM-PLUTO.\n"
        "  3. Move the SAME antenna across to the Pluto.\n"
        "  4. Wait a few seconds for it to enumerate.\n"
    )
    input("Press Enter once the Pluto is connected and the antenna is moved... ")

    try:
        pluto_stats = _capture_pluto(args.duration, args.pluto_gain)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.error("Pluto capture failed: %s", exc)
        line = "=" * 66
        print(f"\n{line}")
        print(
            f"  HackRF One (Pluto run failed): {hackrf_stats.valid_frames} "
            f"frames ({hackrf_stats.frames_per_min:.1f}/min), "
            f"{hackrf_stats.unique_aircraft} aircraft."
        )
        print(f"{line}\n")
        return 1

    _print_summary(hackrf_stats, pluto_stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
