"""Check dashboard server launch options without starting threads or binding ports."""

from unittest.mock import patch

import dashboard.server as server


def test_run_flask_allows_werkzeug_without_tty() -> None:
    """Allow background Werkzeug launches while keeping debugging and reload off."""
    saved_device = server._device_ref
    saved_scanner = server._scanner_ref
    try:
        with (
            patch("dashboard.server.threading.Thread") as thread,
            patch("dashboard.server.socketio.run") as run,
        ):
            server.start_server("127.0.0.1", 5000, device=None, scanner=None)
            targets = [
                call.kwargs["target"]
                for call in thread.call_args_list
                if call.kwargs["target"].__name__ == "run_flask"
            ]
            assert len(targets) == 1
            targets[0]()
            run.assert_called_once_with(
                server.app,
                host="127.0.0.1",
                port=5000,
                allow_unsafe_werkzeug=True,
                debug=False,
                use_reloader=False,
            )
    finally:
        server._device_ref = saved_device
        server._scanner_ref = saved_scanner
