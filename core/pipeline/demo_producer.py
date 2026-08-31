"""
core/pipeline/demo_producer.py — Demo-mode fingerprint producer

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
-------------------
A daemon-thread producer that loops through one or more SigMF capture
files, fingerprints each chunk, embeds it, annotates it with a stable
demo key, and pushes the same queue item shape that ``ScanRunner``'s
``_scan_loop`` produces. Demo mode therefore drives the dashboard through
the real AI loop without opening any SDR hardware or calling a live LLM.

The producer owns NO device, makes NO network calls, and does NOT write
to the vector store. It only reads existing files and feeds the scanner
queue.

ITEM SHAPE
----------
Each queued item is a dict with keys:
    freq_hz     : float  — centre frequency from the first demo file.
    fingerprint : dict   — output of ``fingerprint_samples()``.
    vector      : list   — normalised embedding vector.
    psd_db      : np.ndarray — the averaged PSD trace.

The fingerprint is annotated with ``mimir:demo_key = "<file_id>:<chunk_idx>"``
so ``DemoSignalClassifier`` can look up the cached classification.

LOOP BEHAVIOUR
--------------
Files are replayed in order indefinitely until ``stop()`` is called.
Each chunk is preceded by ``DEMO_CHUNK_INTERVAL_SEC`` (a hardcoded
constant, NOT ``config.dwell_time_sec``) so production paces itself at
roughly two chunks per second. The constant is independent of the
live-scanning-only throttle because disk replay has no hardware-imposed
floor; inheriting config.dwell_time_sec would flood the queue. The queue is fed with
``q.put()`` (blocking, never dropping chunks) — this is deliberately
NOT "latest wins"; demo playback should not discard chunks.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Callable

import sigmf

from core.config.loader import MimirConfig
from core.pipeline.fft import compute_psd
from core.pipeline.fingerprint import fingerprint_from_psd
from core.pipeline.replay import (
    MAX_ONE_SHOT_SAMPLES,
    ReplayFileError,
    _load_sigmf,
    _resolve_band,
    _validate_sequence,
)
from core.pipeline.scanner import ScanRunner
from embeddings.embedder import SpectrumEmbedder

logger = logging.getLogger(__name__)


# DemoProducer's per-chunk pacing. Independent of config.dwell_time_sec,
# which is a LIVE-scanning-only throttle (typically 0.0 — no artificial
# delay — because live SDR acquisition has its own hardware-imposed
# floor). For demo mode, reading pre-recorded samples from disk has no
# such floor: inheriting dwell_time_sec would mean sleep(0.0), flooding
# the queue at raw compute speed (dozens of chunks per second), starving
# the AI loop and overwhelming a human audience. A fixed ~0.5 s gives
# ~2 chunks/sec — fast enough for a ~550-chunk demo file to loop in
# ~5 minutes while remaining watchable. Hardcoded per the Phase 76 fix
# scope (no --demo-speed flag added in this fix; a configurable pace
# remains a legitimate future enhancement).
DEMO_CHUNK_INTERVAL_SEC: float = 0.05


class DemoProducer:
    """Daemon-thread producer that replays SigMF files into the AI pipeline."""

    def __init__(
        self,
        sigmf_files: list[Path],
        embedder: SpectrumEmbedder,
        scanner: ScanRunner,
        config: MimirConfig,
        broadcast_spectrum_fn: Callable | None = None,
    ) -> None:
        """Initialise the demo producer.

        Args:
            sigmf_files: One or more .sigmf-meta files to replay. Each must
                exist and be a valid Mimir SigMF capture (one-shot or
                record-mode). Missing files raise ``FileNotFoundError`` at
                startup; malformed files raise ``ReplayFileError``.
            embedder: ``SpectrumEmbedder`` instance for fingerprint
                vectorisation.
            scanner: ``ScanRunner`` instance whose queue will be fed.
            config: ``MimirConfig`` instance. The pacing knob
                ``dwell_time_sec`` is NOT used by the demo producer; see
                ``DEMO_CHUNK_INTERVAL_SEC`` at module scope for the
                demo-specific pace.
            broadcast_spectrum_fn: Optional callback matching
                ``_broadcast_spectrum_fn`` signature. Wrapped in try/except
                so broadcast failures do not kill the producer thread.
        """
        if not sigmf_files:
            raise ValueError("sigmf_files must contain at least one path")

        for path in sigmf_files:
            if not path.exists():
                raise FileNotFoundError(f"Demo file not found: {path}")

        self._sigmf_files: list[Path] = [Path(p) for p in sigmf_files]
        self._embedder = embedder
        self._scanner = scanner
        self._config = config
        self._broadcast_spectrum_fn = broadcast_spectrum_fn

        self._file_infos: dict[Path, dict] = {}
        self._load_file_infos()

        first_path = self._sigmf_files[0]
        first_info = self._file_infos[first_path]
        first_meta = first_info["meta"]

        captures = first_meta.get_captures()
        core_freq = captures[0].get("core:frequency") if captures else None
        if core_freq is None:
            raise ReplayFileError(
                f"{first_path}: SigMF metadata has no core:frequency capture field"
            )
        self._core_freq_hz = float(core_freq)
        self._sample_rate_hz = float(first_meta.sample_rate)

        band_key, band_match = _resolve_band(self._core_freq_hz)
        if band_key is None:
            raise ReplayFileError(
                f"{first_path}: could not resolve a BAND_PROFILES band for "
                f"{self._core_freq_hz:.0f} Hz"
            )
        self._band_key = band_key

        self._device_driver = (
            first_meta.get_global_field("mimir:device_profile") or "hackrf"
        )

        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started: bool = False

    def _load_file_infos(self) -> None:
        """Pre-load every file's metadata, file_id, and chunk count."""
        for path in self._sigmf_files:
            meta = _load_sigmf(path)
            total_samples = int(meta.sample_count or 0)
            file_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()

            saved_single = meta.get_global_field("mimir:fingerprint")
            saved_sequence = meta.get_global_field("mimir:fingerprint_sequence")

            if saved_sequence is not None:
                sequence = _validate_sequence(saved_sequence, total_samples)
                self._file_infos[path] = {
                    "meta": meta,
                    "file_id": file_id,
                    "mode": "record-mode",
                    "sequence": sequence,
                    "chunk_count": len(sequence),
                }
            elif saved_single is not None:
                if total_samples > MAX_ONE_SHOT_SAMPLES:
                    raise ReplayFileError(
                        f"{path}: one-shot replay refused: file implies "
                        f"{total_samples} samples, exceeding the "
                        f"{MAX_ONE_SHOT_SAMPLES}-sample cap"
                    )
                self._file_infos[path] = {
                    "meta": meta,
                    "file_id": file_id,
                    "mode": "one-shot",
                    "sequence": None,
                    "chunk_count": 1,
                }
            else:
                raise ReplayFileError(
                    f"{path}: SigMF file carries neither mimir:fingerprint nor "
                    f"mimir:fingerprint_sequence"
                )

    def start(self) -> None:
        """Spawn the daemon replay thread. Idempotent: second call is a no-op."""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="demo-producer",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the replay thread to exit at the next safe point."""
        self._stop_event.set()

    def _run(self) -> None:
        """Thread body: loop files indefinitely until ``stop()`` is called."""
        embedder = self._embedder
        scanner = self._scanner
        q = scanner._queue

        while not self._stop_event.is_set():
            for path in self._sigmf_files:
                if self._stop_event.is_set():
                    break
                info = self._file_infos[path]
                meta = info["meta"]
                file_id = info["file_id"]

                if info["mode"] == "record-mode":
                    chunks = info["sequence"]
                    for chunk_idx, entry in enumerate(chunks):
                        if self._stop_event.is_set():
                            break
                        self._produce_chunk(
                            meta=meta,
                            file_id=file_id,
                            chunk_idx=str(chunk_idx),
                            sample_start=entry["sample_start"],
                            sample_count=entry["sample_count"],
                            q=q,
                            embedder=embedder,
                        )
                else:
                    # One-shot: the whole file is a single chunk.
                    if self._stop_event.is_set():
                        break
                    self._produce_chunk(
                        meta=meta,
                        file_id=file_id,
                        chunk_idx="0",
                        sample_start=None,
                        sample_count=-1,
                        q=q,
                        embedder=embedder,
                    )

            if not self._stop_event.is_set():
                logger.info("Demo loop: restarting from file 0")

    def _produce_chunk(
        self,
        meta,
        file_id: str,
        chunk_idx: str,
        sample_start: int | None,
        sample_count: int,
        q,
        embedder,
    ) -> None:
        """Read, fingerprint, embed, and queue one chunk.

        Per-chunk exceptions are logged and swallowed so the demo keeps
        running.
        """
        try:
            time.sleep(DEMO_CHUNK_INTERVAL_SEC)

            if sample_start is None:
                samples = meta.read_samples(count=sample_count)
            else:
                samples = meta.read_samples(
                    start_index=sample_start,
                    count=sample_count,
                )

            psd_result = compute_psd(samples, self._sample_rate_hz, self._core_freq_hz)
            fingerprint = fingerprint_from_psd(
                psd_result,
                self._band_key,
                self._device_driver,
            )
            fingerprint["mimir:demo_key"] = f"{file_id}:{chunk_idx}"
            vector = embedder.embed(fingerprint)

            item = {
                "freq_hz": self._core_freq_hz,
                "fingerprint": fingerprint,
                "vector": vector,
                "psd_db": psd_result["psd_db"],
            }
            q.put(item)

            if self._broadcast_spectrum_fn is not None:
                try:
                    self._broadcast_spectrum_fn(
                        psd_result["psd_db"],
                        self._core_freq_hz,
                        float(psd_result["frequencies_hz"][0]),
                        float(psd_result["frequencies_hz"][-1]),
                    )
                except Exception:
                    logger.exception("Spectrum broadcast failed in demo producer")
        except Exception:
            logger.exception(
                "Demo producer failed to produce chunk %s:%s", file_id, chunk_idx
            )
