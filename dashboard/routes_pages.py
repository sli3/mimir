"""Serve the dashboard's React pages.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""

import os

import dashboard.server as _server


@_server.app.route("/")
def index():
    """Serve the React app for the main dashboard page."""
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


@_server.app.route("/vectordb")
def vector_space_page():
    """Serve the React app for the isolated vector-space visualisation page.

    The /vectordb route is reached directly; the React entry point then
    inspects window.location.pathname and renders VectorSpacePage instead
    of the main dashboard App.

    Returns:
        Flask response: The index.html file for the VectorSpacePage React app.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


@_server.app.route("/radar")
def radar_page():
    """Serve the React app for the isolated radar scope page.

    The /radar route is reached directly; the React entry point
    then inspects window.location.pathname and renders RadarPage
    instead of the main dashboard App.

    Returns:
        Flask response: The index.html file for the RadarPage React app.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )


@_server.app.route("/replay")
def replay_page():
    """Serve the React app for the replay page.

    The /replay route is reached directly; the React entry point
    then inspects window.location.pathname and renders ReplayPage
    instead of the main dashboard App.

    Returns:
        Flask response: The index.html file for the ReplayPage React app.
    """
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "static"),
        "index.html"
    )
