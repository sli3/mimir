"""Provide the stored-vector projection route for the dashboard.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import logging

import numpy as np
from flask import jsonify

import dashboard.server as _server

logger = logging.getLogger(__name__)


@_server.app.route("/api/vectorstore/points")
def api_vectorstore_points():
    """Return all stored ChromaDB embeddings projected into 3D.

    This endpoint is read-only: it pulls existing vectors and metadata from
    the SignalStore and applies scikit-learn dimensionality reduction so the
    frontend can render the vector space as an interactive 3D scatter plot.

    Reduction strategy:
        * n == 0        -> empty response (no computation).
        * 1 <= n < 5    -> PCA to 3 components (t-SNE is unstable this small).
        * n >= 5        -> t-SNE with fixed random_state=42 for reproducible
                          demo layouts; perplexity is capped at min(30, n-1)
                          because t-SNE requires perplexity < n_samples.

    The resulting 3D coordinates are normalised to roughly [-10, 10] on each
    axis so the camera framing is stable regardless of raw magnitudes.

    Frequency metadata handling:
        * Seed data (RTL-ML) uses "center_freq_hz" key
        * Live captures (capture_to_vectorstore.py) use "freq_hz" key
        * The endpoint reads "center_freq_hz" first, falling back to "freq_hz"
          to support both record types and ensure the /vectordb tooltip FREQ field
          displays correctly for seeded records.

    Returns:
        JSON: {"status": "ok"|"empty", "count": int, "method": str|null,
               "points": [{id, x, y, z, label, frequency_hz, snr_db,
               peak_power_db, timestamp}, ...]}
    """
    try:
        store = _server._get_signal_store()

        with _server._VECTORSTORE_CACHE_LOCK:
            cached_count = _server._VECTORSTORE_CACHE["count"]
            cached_points = _server._VECTORSTORE_CACHE["points"]
            cached_method = _server._VECTORSTORE_CACHE["method"]
            if cached_count >= 0 and cached_points is not None:
                return jsonify({
                    "status": "ok",
                    "count": cached_count,
                    "method": cached_method,
                    "points": cached_points,
                }), 200

        # Cache miss: read embeddings and compute the projection.  This runs
        # under the cache lock so concurrent requests don't start multiple
        # expensive t-SNE jobs.
        with _server._VECTORSTORE_CACHE_LOCK:
            raw = store.get_all_embeddings()
            ids = raw["ids"]
            embeddings = raw["embeddings"]
            metadatas = raw["metadatas"]
            n = len(ids)

            if n == 0:
                return jsonify({
                    "status": "empty",
                    "count": 0,
                    "method": None,
                    "points": [],
                }), 200

            matrix = np.array(embeddings, dtype=float)

            # Lazy import scikit-learn so scan.py startup is not penalised for
            # a visualisation endpoint that is rarely hit.
            from sklearn.decomposition import PCA
            from sklearn.manifold import TSNE

            if n == 1:
                projected = np.zeros((1, 3), dtype=float)
                method = "pca"
            elif n < 5:
                n_components = min(3, n)
                reducer = PCA(n_components=n_components, random_state=42)
                method = "pca"
                projected = reducer.fit_transform(matrix)
                if projected.shape[1] < 3:
                    projected = np.pad(
                        projected,
                        ((0, 0), (0, 3 - projected.shape[1])),
                        mode="constant",
                    )
            else:
                reducer = TSNE(
                    n_components=3,
                    random_state=42,
                    perplexity=min(30, n - 1),
                )
                method = "tsne"
                projected = reducer.fit_transform(matrix)

            max_abs = np.max(np.abs(projected))
            if max_abs > 0:
                projected = (projected / max_abs) * 10.0

            points = []
            for i, record_id in enumerate(ids):
                meta = metadatas[i] or {}
                points.append({
                    "id": record_id,
                    "x": float(projected[i, 0]),
                    "y": float(projected[i, 1]),
                    "z": float(projected[i, 2]),
                    "label": str(meta.get("label") or "unknown"),
                    # Seed data uses "center_freq_hz"; live captures use "freq_hz".
                    "frequency_hz": meta.get("center_freq_hz", meta.get("freq_hz")),
                    "snr_db": meta.get("snr_db"),
                    "peak_power_db": meta.get("peak_power_db"),
                    "timestamp": meta.get("timestamp"),
                })

            _server._VECTORSTORE_CACHE["count"] = n
            _server._VECTORSTORE_CACHE["points"] = points
            _server._VECTORSTORE_CACHE["method"] = method

            return jsonify({
                "status": "ok",
                "count": n,
                "method": method,
                "points": points,
            }), 200

    except Exception as exc:
        logger.exception("Vector store projection failed: %s", exc)
        return jsonify({"error": "Vector store projection failed"}), 500
