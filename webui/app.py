"""Prototype web reader window for Cadence (pywebview over the system web view)."""

import sys
from pathlib import Path

from system.book_manager import LIBRARY_PATH
from webui.api import Api
from webui.server import MediaServer


def run(debug=False):
    try:
        import webview
    except ImportError as error:
        print("The web reader needs pywebview. Start it with: uv run --extra web main.py --web\n"
              f"Details: {error}", file=sys.stderr)
        return 1
    LIBRARY_PATH.mkdir(exist_ok=True)
    server = MediaServer(lambda: LIBRARY_PATH.resolve()).start()
    api = Api(server)
    webview.create_window("Cadence", server.app_url, js_api=api, width=1360, height=880,
                          min_size=(960, 640), background_color="#FAFAFA", text_select=True)
    try:
        webview.start(debug=debug, private_mode=False, storage_path=str(Path(".cadence-webview").resolve()))
    finally:
        server.stop()
    return 0
