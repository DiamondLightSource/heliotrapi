"""ASGI import target for Gunicorn (`heliotrapi.asgi:app`).

Kept separate from server.py, which several tests import and call
`start_api()` on directly (sometimes after monkeypatching
`initialize_analyses`). An eager module-level `app = start_api()` in
server.py would run real plugin loading - which can do git clone/uv pip
install network calls - at import time, before any test gets a chance to
patch it. This module exists purely so Gunicorn's `--preload` has a plain
import string to load once, before forking workers.
"""

from heliotrapi.server import start_api

app = start_api(debug=False)
