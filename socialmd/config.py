"""
Application configuration.

All paths are resolved so that the app works both as a plain Python
project and as a frozen PyInstaller executable.
"""

import os
import sys


def _is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


# Directory that holds the executable (or the project root in dev mode).
# Runtime files (downloads, cookies.txt, ffmpeg.exe) live next to it.
BASE_DIR = (
    os.path.dirname(sys.executable)
    if _is_frozen()
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Directory that holds bundled read-only assets (templates, static).
BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)


class Config:
    """Central, immutable application settings."""

    APP_NAME = "SOCIAL-MD"
    VERSION = "1.0.0"

    HOST = "127.0.0.1"
    PORT = 5000
    OPEN_BROWSER = True

    # Paths
    BASE_DIR = BASE_DIR
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")
    TEMPLATE_DIR = os.path.join(BUNDLE_DIR, "templates")
    STATIC_DIR = os.path.join(BUNDLE_DIR, "static")

    # Networking
    PROXY = ""                 # e.g. "http://user:pass@host:port" (optional)
    REQUEST_TIMEOUT = 30       # seconds

    # Behaviour
    MAX_PARALLEL_DOWNLOADS = 2
    INFO_CACHE_TTL = 3600      # seconds to cache video metadata
    TASK_RETENTION = 3600      # seconds to keep finished tasks in memory
    MAX_URL_LENGTH = 2048