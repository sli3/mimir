"""
Shared state module for the Mimir dashboard threads.

This module holds all data that needs to be shared between two separate
threads: Thread A (capture_loop) and Thread B (ai_loop).

Why do we need this?
--------------------
In Python, each thread has its own memory space by default. If we want
Thread A to send signal fingerprints to Thread B for AI classification,
we need a way for them to communicate. We use:

1. A queue - like a conveyor belt where Thread A puts items and Thread B takes them
2. A lock - like a doorman that ensures only one thread touches shared data at a time
3. An event - like an alarm that tells both threads when to shut down
4. A dict with defaults - to store the latest AI annotation so the dashboard can display it

No classes here - everything is at module level for simplicity.
"""

import threading
from queue import Queue


# =============================================================================
# SHARED STATE VARIABLES
# =============================================================================

# -----------------------------------------------------------------------------
# fingerprint_queue
# -----------------------------------------------------------------------------
# Type: queue.Queue
# Purpose: Thread-safe queue that passes signal fingerprints from capture_loop
#          (Thread A) to ai_loop (Thread B).
# How it works: Thread A puts() fingerprints here after extracting features.
#               Thread B gets() them one by one and sends to the AI for classification.
# Why a queue?: It's FIFO (first-in-first-out), handles backpressure if ai_loop
#               falls behind, and is thread-safe so no locking is needed.
fingerprint_queue = Queue()

# -----------------------------------------------------------------------------
# annotation_lock
# -----------------------------------------------------------------------------
# Type: threading.Lock
# Purpose: Ensures only one thread can modify latest_annotation at a time.
# How it works: Before reading or writing to latest_annotation, a thread must
#               acquire this lock. After it's done, it releases the lock.
# Why we need it: The dict below is shared between threads. Without a lock,
#                 two threads modifying it simultaneously could corrupt data.
annotation_lock = threading.Lock()

# -----------------------------------------------------------------------------
# latest_annotation
# -----------------------------------------------------------------------------
# Type: dict (with default values)
# Purpose: Stores the most recent AI classification result so the dashboard
#          can display it immediately without waiting for a new fingerprint.
# Keys explained:
#   - label: The AI's predicted signal type (e.g., "FM broadcast", "noise")
#   - confidence: How sure the AI is (0.0 to 1.0), or None if not classified yet
#   - snr_db: Signal-to-noise ratio in decibels, or None
#   - distance: Estimated distance from source in metres, or None
#   - timestamp: When this annotation was created, as a datetime object
# Why defaults?: So the dashboard always has something to show even before
#                the AI has processed any signals. "Scanning..." tells the user
#                what's happening while we wait for data.
latest_annotation = {
    "label": "Scanning...",
    "confidence": None,
    "snr_db": None,
    "distance": None,
    "timestamp": None,
}

# -----------------------------------------------------------------------------
# shutdown_event
# -----------------------------------------------------------------------------
# Type: threading.Event
# Purpose: Signals both threads to stop when the dashboard should close.
# How it works: When set(), thread loops check this and exit gracefully.
#               The dashboard server sets this on shutdown so capture_loop
#               and ai_loop don't keep running in the background.
# Why an event?: It's a simple, standard way to coordinate shutdown across
#                multiple threads without complex locking or shared flags.
shutdown_event = threading.Event()

# =============================================================================
# WEBSOCKET CLIENT MANAGEMENT
# =============================================================================

# Set of active browser WebSocket connections.
# The capture loop broadcasts to every ws in this set.
# Protected by spectrum_clients_lock.
spectrum_clients: set = set()
spectrum_clients_lock = threading.Lock()

# Band switching — event set by /ws/command when user clicks a band button.
# The capture loop checks this every frame and restarts on the new band.
band_change_event = threading.Event()

# The four AU-legal band profiles. All receive-only.
BAND_PROFILES: dict = {
    "fm_broadcast": {
        "center_freq_hz": 98_000_000,
        "lna_gain_db":    32,
        "vga_gain_db":    40,
    },
    "aviation": {
        "center_freq_hz": 127_000_000,
        "lna_gain_db":    32,
        "vga_gain_db":    40,
    },
    "adsb": {
        "center_freq_hz": 1_090_000_000,
        "lna_gain_db":    32,
        "vga_gain_db":    38,
    },
    "noise_floor": {
        "center_freq_hz": 98_000_000,
        "lna_gain_db":    16,
        "vga_gain_db":    20,
    },
}

# Currently active band. Initialise to FM broadcast.
# Protected by current_band_lock.
current_band: dict = dict(BAND_PROFILES["fm_broadcast"])
current_band_lock = threading.Lock()
