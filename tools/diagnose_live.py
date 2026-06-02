"""
diagnose_live.py — Live diagnostic tool for Mimir RF Spectrum Scanner

Connects to the running Mimir Flask/Socket.IO server, listens for live
events, prints structured diagnostic output to stdout, and exits with
PASS or FAIL.

Usage:
    python tools/diagnose_live.py --duration 15 --url http://localhost:5000

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import argparse
import logging
import statistics
import sys
import time
from pathlib import Path

import socketio

logger = logging.getLogger(__name__)

# ANSI block character for strong signal in ASCII bar
_CHAR_STRONG = "\u2588"
# ANSI block character for weak/no signal in ASCII bar
_CHAR_WEAK = "\u2591"
# dBFS threshold above which a frequency fraction is considered "strong"
_STRONG_THRESHOLD_DB = -60.0
# Default ASCII bar width in characters
_DEFAULT_BAR_WIDTH = 20
# Connection timeout in seconds
_CONNECT_TIMEOUT = 10


def _render_ascii_bar(
    psd_db: list[float], width: int = _DEFAULT_BAR_WIDTH
) -> str:
    """Render an ASCII bar representing signal presence across frequency bins.

    The PSD bins are divided into *width* equal fractions. For each fraction,
    if the maximum dBFS value exceeds ``_STRONG_THRESHOLD_DB`` (-60 dBFS),
    the character is ``_CHAR_STRONG`` (█), otherwise ``_CHAR_WEAK`` (░).

    Args:
        psd_db: List of PSD values in dBFS.
        width: Character width of the bar (default 20).

    Returns:
        A string of *width* characters representing relative signal strength.
    """
    n = len(psd_db)
    if n == 0 or width <= 0:
        return _CHAR_WEAK * max(width, 0)

    chars: list[str] = []
    for i in range(width):
        start = i * n // width
        end = max((i + 1) * n // width, start + 1)
        segment = psd_db[start:end]
        if segment and max(segment) > _STRONG_THRESHOLD_DB:
            chars.append(_CHAR_STRONG)
        else:
            chars.append(_CHAR_WEAK)
    return "".join(chars)


class DiagnosticSession:
    """Manages a diagnostic session connecting to the Mimir server.

    Connects via Socket.IO, registers event handlers for ``spectrum_update``
    and ``scan_result``, tracks statistics, and determines PASS/FAIL status.

    Attributes:
        spectrum_update_count: Number of ``spectrum_update`` events received.
        scan_result_count: Number of ``scan_result`` events received.
        spectrum_timestamps: Timestamps of received ``spectrum_update`` events.
        connection_error: Whether a connection error occurred.
    """

    def __init__(self, url: str, duration: int) -> None:
        """Initialise the diagnostic session.

        Args:
            url: Server URL (e.g. http://localhost:5000).
            duration: Run duration in seconds.
        """
        self.url: str = url
        self.duration: int = duration
        self.spectrum_update_count: int = 0
        self.scan_result_count: int = 0
        self.spectrum_timestamps: list[float] = []
        self.connection_error: bool = False

        self._client: socketio.Client = socketio.Client(request_timeout=_CONNECT_TIMEOUT)
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register Socket.IO event handlers on the client."""
        self._client.on("spectrum_update", self._on_spectrum_update)
        self._client.on("scan_result", self._on_scan_result)

        @self._client.event
        def connect() -> None:
            logger.info("Connected to %s", self.url)

        @self._client.event
        def connect_error(data: dict) -> None:
            logger.error("Connection error: %s", data)
            self.connection_error = True

    def _on_spectrum_update(self, data: dict) -> None:
        """Handle a ``spectrum_update`` event from the server.

        Prints a structured line to stdout with bin count, min/max dBFS,
        and an ASCII bar showing relative signal strength.

        Args:
            data: Event payload containing ``center_freq_hz`` and ``psd_db``.
        """
        self.spectrum_update_count += 1
        self.spectrum_timestamps.append(time.time())
        psd = data.get("psd_db", [])
        if not psd:
            return
        bar = _render_ascii_bar(psd)
        min_db = min(psd)
        max_db = max(psd)
        print(
            f"[spectrum_update] bins={len(psd)} "
            f"min={min_db:.1f}dBFS "
            f"max={max_db:.1f}dBFS "
            f"[{bar}]"
        )

    def _on_scan_result(self, data: dict) -> None:
        """Handle a ``scan_result`` event from the server.

        Prints a structured line to stdout with frequency, signal type,
        confidence, and novelty status.

        Args:
            data: Event payload with ``center_freq_hz``, ``signal_type``,
                ``confidence``, and ``novel`` fields.
        """
        self.scan_result_count += 1
        freq_hz = data.get("center_freq_hz", 0)
        signal_type = data.get("signal_type", "unknown")
        confidence = data.get("confidence", "unknown")
        novel = data.get("novel", False)
        freq_mhz = freq_hz / 1e6
        print(
            f"[scan_result] freq={freq_mhz:.3f}MHz "
            f"type={signal_type} "
            f"conf={confidence} "
            f"novel={novel}"
        )

    def run(self) -> int:
        """Run the diagnostic session.

        Connects to the server, listens for events for the configured
        duration, then determines PASS/FAIL status.

        Returns:
            0 if PASS (>=1 ``spectrum_update``, >=1 ``scan_result``,
                no connection error), 1 otherwise.
        """
        logger.info("Connecting to %s ...", self.url)
        try:
            self._client.connect(self.url)
        except socketio.exceptions.ConnectionError as err:
            logger.error("Failed to connect: %s", err)
            self.connection_error = True
            self._print_summary()
            return 1

        logger.info(
            "Listening for %d seconds (Ctrl+C to abort)...", self.duration
        )
        try:
            self._client.sleep(self.duration)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        self._client.disconnect()
        self._print_summary()
        return self._determine_exit_code()

    def _determine_exit_code(self) -> int:
        """Determine exit code based on session results.

        Returns:
            0 if PASS criteria met, 1 otherwise.
        """
        if self.connection_error:
            return 1
        if self.spectrum_update_count < 1:
            return 1
        if self.scan_result_count < 1:
            return 1
        return 0

    def _compute_gaps(self) -> dict:
        """Analyse inter-event gaps for irregularities.

        Computes gaps between consecutive ``spectrum_update`` timestamps
        and flags any gap exceeding 5x the median interval.

        Returns:
            Dict with keys:
                - ``gaps_found`` (bool): True if any large gap detected.
                - ``num_large_gaps`` (int): Count of large gaps.
                - ``large_gaps`` (list[float]): Gap durations > 5x median.
                - ``median_gap`` (float): Median inter-event interval.
                - ``num_gaps`` (int): Total number of gaps analysed.
        """
        if len(self.spectrum_timestamps) < 2:
            return {
                "gaps_found": False,
                "num_large_gaps": 0,
                "large_gaps": [],
                "median_gap": 0.0,
                "num_gaps": 0,
            }

        gaps = [
            self.spectrum_timestamps[i] - self.spectrum_timestamps[i - 1]
            for i in range(1, len(self.spectrum_timestamps))
        ]
        median_gap = statistics.median(gaps)
        if median_gap <= 0:
            return {
                "gaps_found": False,
                "num_large_gaps": 0,
                "large_gaps": [],
                "median_gap": median_gap,
                "num_gaps": len(gaps),
            }
        large_gaps = [g for g in gaps if g > 5 * median_gap]
        return {
            "gaps_found": len(large_gaps) > 0,
            "num_large_gaps": len(large_gaps),
            "large_gaps": large_gaps,
            "median_gap": median_gap,
            "num_gaps": len(gaps),
        }

    def _print_summary(self) -> None:
        """Print diagnostic summary to stderr via logging."""
        duration = max(self.duration, 0.001)
        rate = self.spectrum_update_count / duration

        logger.info("=" * 40)
        logger.info("DIAGNOSTIC SUMMARY")
        logger.info("=" * 40)
        status = "PASS" if self._determine_exit_code() == 0 else "FAIL"
        logger.info("Status: %s", status)
        logger.info("Connection error: %s", self.connection_error)
        logger.info("Spectrum updates: %d", self.spectrum_update_count)
        logger.info("Scan results: %d", self.scan_result_count)
        logger.info("Event rate: %.2f events/sec", rate)

        gap_result = self._compute_gaps()
        if gap_result["gaps_found"]:
            logger.warning(
                "Gap detection: %d gaps >5x median interval detected",
                gap_result["num_large_gaps"],
            )
            for idx, gap in enumerate(gap_result["large_gaps"], 1):
                logger.warning("  Gap %d: %.2fs", idx, gap)
        else:
            logger.info(
                "Gap detection: No significant gaps (%d gaps analysed)",
                gap_result["num_gaps"],
            )

        if status == "PASS":
            logger.info("All checks passed.")
        else:
            logger.info("Some checks failed.")
        logger.info("=" * 40)


def parse_args(args: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        args: Command-line argument list (typically ``sys.argv[1:]``).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Live diagnostic tool for Mimir RF Spectrum Scanner"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Run duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:5000",
        help="Server URL (default: http://localhost:5000)",
    )
    return parser.parse_args(args)


def main() -> None:
    """Main entry point for the diagnostic tool."""
    args = parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    session = DiagnosticSession(url=args.url, duration=args.duration)
    sys.exit(session.run())


if __name__ == "__main__":
    main()
