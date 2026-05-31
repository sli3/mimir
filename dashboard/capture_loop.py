"""
Thread A — Fast capture loop for real-time spectrum streaming.

This module runs in a separate thread from the dashboard server's event loop,
but communicates via WebSocket to the browser. Each WebSocket connection
represents one browser client that wants to see live spectrum data.

Why do we need this?
--------------------
The HackRF captures raw radio signals continuously. We need to:
1. Grab samples quickly (as fast as hardware allows)
2. Convert them to frequency domain using FFT (shows power at each frequency)
3. Send the results to the browser in real-time

Think of it like a camera taking photos and showing them on a screen.
The HackRF is the camera, this loop takes the "photos" of the spectrum,
and WebSocket is how we display them instantly on your computer screen.

How it works:
-------------
- Browser connects to /ws/spectrum endpoint
- This function runs in FastAPI's async event loop
- Loop runs forever until either:
  - The browser disconnects (user closes tab or crashes)
  - shutdown_event is set (user stops the dashboard)
- Each iteration captures 2 million IQ samples, runs FFT, sends results

Important note for beginners:
-----------------------------
"IQ samples" = complex numbers that represent the radio signal.
Each sample has a real part (I) and imaginary part (Q). Together they
encode both how strong the signal is AND its phase/position in time.
The FFT converts these time-domain samples into frequency domain data,
showing us what frequencies are present and how strong each one is.

Legal: HackRF One is receive-only. This code never transmits anything.
Radiocommunications Act 1992 (Cth) — AU/SA jurisdiction, ACMA authority.
"""

import asyncio
import logging
from datetime import datetime

from fastapi.websockets import WebSocketDisconnect

import dashboard.shared_state as shared_state
from core.device.hackrf_rx import HackRFReceiver
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum

# Configure logging for this module
logger = logging.getLogger(__name__)


async def run_capture_loop(websocket: WebSocket) -> None:
    """
    Run the fast capture loop that streams spectrum data to a browser.

    This function is called when a browser connects to /ws/spectrum.
    It continuously captures IQ samples, computes FFT/PSD, and sends
    results over the WebSocket until disconnected or shutdown.

    Args:
        websocket: The WebSocket connection object from FastAPI.
                   Used to send JSON data to the browser.

    Returns:
        None. Exits cleanly when shutdown_event is set or browser disconnects.
    """
    # Constants for capture — calibrated settings from Phase 4
    CENTER_FREQ_HZ = 98_000_000  # 98 MHz, in the FM broadcast band
    SAMPLE_RATE_HZ = 2_000_000   # 2 million samples per second
    NUM_SAMPLES = 256_000       # Reduced sample count for live display speed — classifier uses full captures
    LNA_GAIN_DB = 32             # Low-noise amplifier gain
    VGA_GAIN_DB = 40             # Variable gain amplifier gain

    logger.info(
        "Capture loop started: freq=%.1f MHz, rate=%.1f MSPS",
        CENTER_FREQ_HZ / 1e6,
        SAMPLE_RATE_HZ / 1e6,
    )

    iteration_count = 0

    # Create ONE HackRFReceiver instance for the entire WebSocket session
    # This prevents SoapySDR overhead from creating/destroying receivers each frame
    sdr = HackRFReceiver(
        center_freq_hz=CENTER_FREQ_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        lna_gain_db=LNA_GAIN_DB,
        vga_gain_db=VGA_GAIN_DB,
    )

    try:
        # Use context manager to ensure proper cleanup on exit
        with sdr:
            while not shared_state.shutdown_event.is_set():
                # Check shutdown before read to allow Ctrl+C to work
                if shared_state.shutdown_event.is_set():
                    break

                # Step 1: Read IQ samples from HackRF One directly
                # Running in thread executor so it doesn't block async event loop
                loop = asyncio.get_event_loop()
                iq_samples = await loop.run_in_executor(
                    None,
                    lambda: sdr.read_samples(NUM_SAMPLES)
                )

                # Check shutdown after read to allow Ctrl+C to work
                if shared_state.shutdown_event.is_set():
                    break

                # Step 2: Compute power spectral density (FFT)
                # Converts time-domain samples to frequency domain
                psd_result = compute_psd(
                    samples=iq_samples,
                    sample_rate_hz=SAMPLE_RATE_HZ,
                    center_freq_hz=CENTER_FREQ_HZ,
                )

                # Step 3: Extract spectral fingerprint features
                # Computes peak frequency, SNR, bandwidth, etc.
                fingerprint = fingerprint_spectrum(
                    psd_result=psd_result,
                )

                # Add timestamp to fingerprint if not present
                if "timestamp" not in fingerprint:
                    fingerprint["timestamp"] = datetime.now().isoformat()

                # Step 4: Build JSON-serialisable dict for browser
                # Convert numpy arrays to Python lists so browser can read them
                spectrum_data = {
                    "type": "spectrum",
                    "frequencies_hz": psd_result["frequencies_hz"].tolist(),
                    "psd_db": psd_result["psd_db"].tolist(),
                    "center_freq_hz": CENTER_FREQ_HZ,
                    "timestamp": fingerprint["timestamp"],
                }

                # Step 5: Send to browser via WebSocket
                await websocket.send_json(spectrum_data)

                # Check shutdown after send_json to allow Ctrl+C to work
                if shared_state.shutdown_event.is_set():
                    break

                # Step 6: Every 20th iteration, put fingerprint in queue for AI thread
                if iteration_count % 20 == 0:
                    try:
                        shared_state.fingerprint_queue.put_nowait(fingerprint)
                    except Exception as e:
                        logger.error("Failed to put fingerprint in queue: %s", e)

                # Step 7: Check shutdown flag before next iteration
                iteration_count += 1

    except WebSocketDisconnect:
        # Browser closed the connection — log and exit cleanly
        logger.info(
            "Browser disconnected from /ws/spectrum after %d iterations",
            iteration_count,
        )
    except Exception as e:
        logger.error("Capture loop error: %s", e, exc_info=True)
        raise
    finally:
        logger.debug("Capture loop cleanup complete")
