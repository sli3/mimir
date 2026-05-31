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

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Mount static files so /static/... URLs work (needed later for JS and CSS)
import dashboard.shared_state as shared_state
from dashboard.capture_loop import run_capture_loop

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
    # Startup event - called when server is starting
    logger.info("Mimir dashboard starting on port 8899")
    yield  # FastAPI resumes here while the server runs
    # Shutdown event - called when server is stopping
    logger.info("Shutting down Mimir dashboard...")
    shared_state.shutdown_event.set()


# Create the FastAPI application
# app is like a container for all our routes and middleware
app = FastAPI(lifespan=lifespan)

# Mount static files so /static/... URLs work (needed later for JS and CSS)
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


@app.get("/")
async def root():
    """Serve the main dashboard HTML page."""
    return FileResponse("dashboard/static/index.html")


# WebSocket endpoint for streaming PSD (power spectral density) data.
@app.websocket("/ws/spectrum")
async def spectrum_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for live spectrum data.

    Accepts a browser connection then hands off to run_capture_loop()
    which streams psd_db rows continuously until disconnect or shutdown.
    """
    await websocket.accept()
    logger.info("Browser connected to /ws/spectrum")
    await run_capture_loop(websocket)


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
    uvicorn.run(app, host="0.0.0.0", port=8899)
