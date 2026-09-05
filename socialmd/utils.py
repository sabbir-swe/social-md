"""Small, dependency-free helper functions."""

from __future__ import annotations

import glob
import os
import re
import shutil
from typing import Optional

PLATFORM_PATTERNS = {
    "youtube": re.compile(r"(youtube\.com|youtu\.be)", re.I),
    "tiktok": re.compile(r"tiktok\.com", re.I),
    "instagram": re.compile(r"instagram\.com", re.I),
    "facebook": re.compile(r"(facebook\.com|fb\.watch|fb\.com)", re.I),
}

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")
_GENERIC_ID_RE = re.compile(r"/(?:video|reel|reels|p|tv|videos|watch|share)/?([A-Za-z0-9_-]{5,})")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_PREFIX_RE = re.compile(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*[\w-]*:\s*)?", re.I)

VALID_HEIGHTS = range(144, 4321)


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #
def detect_platform(url: str) -> str:
    """Return a platform key for the given URL ('other' when unknown)."""
    for name, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return name
    return "other"


def is_valid_url(url: str, max_length: int) -> bool:
    return bool(url) and len(url) <= max_length and bool(_URL_RE.match(url))


def media_key(url: str, platform: str) -> str:
    """Stable, filesystem-safe identifier used for caching downloads."""
    if platform == "youtube":
        match = _YOUTUBE_ID_RE.search(url)
        if match:
            return match.group(1)
    match = _GENERIC_ID_RE.search(url)
    if match:
        return f"{platform}_{match.group(1)}"
    return f"{platform}_" + re.sub(r"[^A-Za-z0-9]", "", url)[-24:]


def parse_quality(value) -> str | int:
    """Validate a quality selector. Returns 'best', 'audio' or an int height."""
    if value in ("best", "audio"):
        return value
    try:
        height = int(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid quality selector.")
    if height not in VALID_HEIGHTS:
        raise ValueError("Quality is out of range.")
    return height


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #
def find_ffmpeg(base_dir: str) -> Optional[str]:
    """
    Locate FFmpeg.

    Returns the directory to pass as ``ffmpeg_location`` when a local binary
    sits next to the app, an empty string when FFmpeg is available on PATH,
    or ``None`` when it cannot be found.
    """
    for name in ("ffmpeg.exe", "ffmpeg"):
        if os.path.isfile(os.path.join(base_dir, name)):
            return base_dir
    return "" if shutil.which("ffmpeg") else None


def find_output_file(folder: str, quality) -> Optional[str]:
    """Return the most recent finished media file inside ``folder``."""
    skip = (".part", ".ytdl", ".json", ".jpg", ".webp", ".png")
    files = [f for f in glob.glob(os.path.join(folder, "*")) if not f.endswith(skip)]
    if not files:
        return None
    wanted = ".mp3" if quality == "audio" else ".mp4"
    preferred = [f for f in files if f.lower().endswith(wanted)] or files
    return max(preferred, key=os.path.getmtime)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def human_speed(bytes_per_second) -> str:
    if not bytes_per_second:
        return ""
    value = float(bytes_per_second)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB/s"


def human_eta(seconds) -> str:
    if not seconds or seconds < 0:
        return ""
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m left"
    if minutes:
        return f"{minutes}m {sec:02d}s left"
    return f"{sec}s left"


# --------------------------------------------------------------------------- #
# Error helpers
# --------------------------------------------------------------------------- #
def friendly_error(exc: BaseException | str, platform: str = "other") -> str:
    """Translate a raw yt-dlp/FFmpeg error into a clear, actionable message."""
    raw = _ANSI_RE.sub("", str(exc))
    lower = raw.lower()
    site = platform.title() if platform != "other" else "This site"

    if "not a bot" in lower or "sign in to confirm" in lower:
        return ("YouTube flagged this request as automated. Update yt-dlp "
                "(pip install -U yt-dlp), place a cookies.txt file next to the app, "
                "disable any VPN and try again.")
    if "login required" in lower or "rate-limit" in lower or "requested content is not available" in lower:
        return (f"{site} requires a logged-in session. Export your browser cookies "
                "to cookies.txt (next to the app) and try again.")
    if "private" in lower:
        return "This video is private. Only a cookies.txt from an account with access can download it."
    if "ffmpeg" in lower:
        return "FFmpeg was not found. Install FFmpeg or place ffmpeg.exe next to the app."
    if "unsupported url" in lower:
        return "This link is not supported. Please paste a direct link to a video."
    if "video unavailable" in lower or "has been removed" in lower or "geo" in lower:
        return "This video is unavailable, removed, or blocked in your region."
    if "no video" in lower or "photo" in lower:
        return "This post does not contain a video."

    cleaned = _PREFIX_RE.sub("", raw).strip()
    return cleaned[:300] or "Something went wrong. Please try again."