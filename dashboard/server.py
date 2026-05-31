"""
FastAPI server for the Mimir RF spectrum dashboard.

This module runs a web server that:
1. Serves the dashboard HTML page
2. Provides WebSocket endpoints for real-time data streaming

The server starts independently of the capture and AI threads. Those threads
are started separately when needed (in the future, via config or CLI flag).

Why FastAPI?
------------
FastAPI is modern, fast, and easy to use. It handles:
- HTTP requests (serving HTML files)
- WebSocket connections (real-time streaming of data)
- Automatic documentation (but we're not using that feature yet)

Beginner note:
--------------
A "WebSocket" is a persistent connection between browser and server. Unlike
regular HTTP where the connection closes after each request, WebSockets stay
open so we can push live data (PSD values, AI annotations) to the dashboard
without asking for it repeatedly.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Mount static files so /static/... URLs work (needed later for JS and CSS)
import dashboard.shared_state as shared_state
from dashboard.capture_loop import run_shared_capture_loop
from dashboard.shared_state import (
    BAND_PROFILES,
    band_change_event,
    current_band,
    current_band_lock,
    spectrum_clients,
    spectrum_clients_lock,
)

# Configure logging - beginner note: logging is like printing to the terminal
# but with timestamps and levels (INFO, WARNING, ERROR). We use it so you
# can see what the server is doing.
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Server lifecycle management - runs when server starts and stops.

    This function handles startup and shutdown events for the FastAPI app.
    "Lifespan" is a special context manager that FastAPI calls automatically.

    On startup:
    - Log that the dashboard is starting
    - Do NOT start capture_loop or ai_loop yet (those are separate threads)

    On shutdown:
    - Tell all threads to stop by setting the shutdown_event flag
    """
    logger.info("Mimir dashboard starting on port 8899")
    capture_task = asyncio.create_task(run_shared_capture_loop())
    yield
    shared_state.shutdown_event.set()
    try:
        await asyncio.wait_for(capture_task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("Capture task did not exit after 5s -- force cancelling")
        capture_task.cancel()
        try:
            await capture_task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass


# Create the FastAPI application
# app is like a container for all our routes and middleware
app = FastAPI(lifespan=lifespan)

# Mount static files so /static/... URLs work (needed later for JS and CSS)
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


@app.get("/")
async def root():
    """Serve the main dashboard HTML page."""
    return FileResponse("dashboard/static/index.html")


@app.websocket("/ws/spectrum")
async def spectrum_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    with spectrum_clients_lock:
        spectrum_clients.add(websocket)
    logger.info("Browser connected -- %d client(s) active", len(spectrum_clients))
    try:
        while not shared_state.shutdown_event.is_set():
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        with spectrum_clients_lock:
            spectrum_clients.discard(websocket)
        logger.info("Browser disconnected -- %d client(s) remaining", len(spectrum_clients))


@app.websocket("/ws/command")
async def command_ws(websocket: WebSocket) -> None:
    """Receives band-switch commands from the browser band selector buttons."""
    await websocket.accept()
    try:
        async for message in websocket.iter_text():
            import json as _json
            try:
                cmd = _json.loads(message)
                band_name = cmd.get("band")
                if band_name in BAND_PROFILES:
                    with current_band_lock:
                        current_band.clear()
                        current_band.update(BAND_PROFILES[band_name])
                    band_change_event.set()
                    logger.info("Band switched to %s", band_name)
                    await websocket.send_text(
                        _json.dumps({"status": "ok", "band": band_name})
                    )
                else:
                    await websocket.send_text(
                        _json.dumps({"status": "error", "message": f"Unknown band: {band_name}"})
                    )
            except Exception as exc:
                logger.error("Command error: %s", exc)
    except WebSocketDisconnect:
        pass


# WebSocket endpoint for streaming AI classification annotations.
# Currently not implemented - just accepts connections and sends a status message.
@app.websocket("/ws/classify")
async def classify_websocket(websocket: WebSocket):
    """
    WebSocket connection for real-time AI classifications.

    Clients connect here to receive classification results from the AI model.
    Each message contains: label, confidence, SNR, distance, timestamp.

    What happens when a client connects?
    - Accept the connection
    - Send {"status": "not yet implemented"} immediately
    - Keep the connection open waiting for future annotations to stream

    Future implementation will:
    - Read from fingerprint_queue (ai_loop processes fingerprints here)
    - Pass results through LLM classification
    - Stream annotated results as JSON objects over this WebSocket
    """
    await websocket.accept()
    await websocket.send_json({"status": "not yet implemented"})
    # Connection stays open here, waiting for future data


if __name__ == "__main__":
    import uvicorn

    # Run the server locally for development
    # host=0.0.0.0 means accept connections from any network interface
    # port=8899 is our chosen port (not conflicting with common services)
    # reload=True enables auto-reload on code changes (convenient for dev)
    uvicorn.run(app, host="0.0.0.0", port=8899, loop="asyncio")
