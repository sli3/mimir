"""
dashboard/capture_loop.py

Single shared HackRF capture loop.

Opens the HackRF ONCE for the entire server lifetime.
Reads spectrum data continuously and broadcasts JSON messages to
every browser WebSocket in spectrum_clients.
Restarts cleanly when the user switches bands via /ws/command.

No TX. No TX flags. No TX config. Receive only.
"""
import asyncio
import json
import logging

from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from core.device.hackrf_rx import HackRFReceiver
from dashboard.server import start_server
from dashboard.shared_state import (
    fingerprint_queue,
    shutdown_event,
    spectrum_clients,
    spectrum_clients_lock,
    band_change_event,
    current_band,
    current_band_lock,
)

logger = logging.getLogger(__name__)

NUM_SAMPLES = 65_536
SAMPLE_RATE_HZ = 2_000_000
FINGERPRINT_EVERY_N_FRAMES = 20


async def run_shared_capture_loop() -> None:
    """
    Outer loop: opens HackRF, runs inner read loop, restarts on band change.
    Exits cleanly when shutdown_event is set.
    """
    frame_count = 0

    while not shutdown_event.is_set():

        # Snapshot the current band settings under the lock.
        with current_band_lock:
            band = dict(current_band)

        band_change_event.clear()

        logger.info(
            "Opening HackRF at %.3f MHz  LNA=%d  VGA=%d",
            band["center_freq_hz"] / 1e6,
            band["lna_gain_db"],
            band["vga_gain_db"],
        )

        loop = asyncio.get_event_loop()
        sdr = None
        try:
            # Open in executor -- keeps event loop free during USB init
            sdr = await loop.run_in_executor(
                None,
                lambda: HackRFReceiver(
                    center_freq_hz=band["center_freq_hz"],
                    sample_rate_hz=SAMPLE_RATE_HZ,
                    lna_gain_db=band["lna_gain_db"],
                    vga_gain_db=band["vga_gain_db"],
                ).__enter__()
            )

            while not shutdown_event.is_set() and not band_change_event.is_set():
                samples = await loop.run_in_executor(
                    None, sdr.read_samples, NUM_SAMPLES
                )

                if shutdown_event.is_set():
                    break

                psd_result = compute_psd(
                    samples,
                    sample_rate_hz=SAMPLE_RATE_HZ,
                    center_freq_hz=band["center_freq_hz"],
                )

                msg = json.dumps({
                    "psd_db":         psd_result["psd_db"].tolist(),
                    "freq_min_hz":    float(psd_result["frequencies_hz"][0]),
                    "freq_max_hz":    float(psd_result["frequencies_hz"][-1]),
                    "center_freq_hz": band["center_freq_hz"],
                })

                dead: set = set()
                with spectrum_clients_lock:
                    snapshot = set(spectrum_clients)

                broadcast_spectrum = getattr(start_server, "_broadcast_spectrum_fn", None)
                if broadcast_spectrum is not None:
                    broadcast_spectrum(
                        psd_db=psd_result["psd_db"].tolist(),
                        center_freq_hz=band["center_freq_hz"],
                        freq_min_hz=float(psd_result["frequencies_hz"][0]),
                        freq_max_hz=float(psd_result["frequencies_hz"][-1]),
                    )

                for ws in snapshot:
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        dead.add(ws)

                if dead:
                    with spectrum_clients_lock:
                        spectrum_clients.difference_update(dead)

                frame_count += 1
                if frame_count % FINGERPRINT_EVERY_N_FRAMES == 0:
                    fingerprint = fingerprint_spectrum(psd_result)
                    if not fingerprint_queue.full():
                        fingerprint_queue.put_nowait(fingerprint)

        except Exception as exc:
            logger.error("HackRF error in capture loop: %s -- retrying in 2 s", exc)
            await asyncio.sleep(2.0)
        finally:
            # Close in executor -- keeps event loop free during USB teardown
            if sdr is not None:
                await loop.run_in_executor(
                    None,
                    lambda: HackRFReceiver.__exit__(sdr, None, None, None)
                )

    logger.info("Capture loop shut down cleanly.")
