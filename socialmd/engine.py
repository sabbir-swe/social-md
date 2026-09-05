"""
Download engine built on top of yt-dlp.

Responsibilities:
  * Detect the platform and build the right yt-dlp options.
  * Retry transient failures automatically, then fall back to alternative
    extractor configurations / cookies when a request is blocked.
  * Cache metadata and finished files so repeated requests never hit the network.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Iterator, Optional

import yt_dlp

from .config import Config
from .utils import (
    detect_platform,
    find_ffmpeg,
    find_output_file,
    friendly_error,
    human_eta,
    human_speed,
    media_key,
)

log = logging.getLogger("socialmd.engine")

ProgressCallback = Callable[..., None]
ExtractorArgs = Optional[dict]

# ---------------------------------------------------------------------------
# Attempt configurations
# ---------------------------------------------------------------------------
# YouTube: player clients tried in order when the default one is blocked.
YOUTUBE_VARIANTS: list[ExtractorArgs] = [
    None,
    {"youtube": {"player_client": ["ios"]}},
    {"youtube": {"player_client": ["tv"]}},
    {"youtube": {"player_client": ["mweb"]}},
    {"youtube": {"player_client": ["web_safari"]}},
    {"youtube": {"player_client": ["android_vr"]}},
]

# TikTok: alternative API hosts used when web-page extraction fails.
TIKTOK_VARIANTS: list[ExtractorArgs] = [
    None,
    {"tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}},
    {"tiktok": {"api_hostname": ["api16-normal-c-useast1a.tiktokv.com"]}},
]

# Errors that are usually temporary: retry the *same* configuration first.
TRANSIENT_MARKERS = (
    "rehydration", "universal data", "unable to extract webpage",
    "timed out", "reset by peer", "empty media response",
    "connection aborted", "remote end closed", "temporarily",
)

# Errors that justify switching to another configuration.
RETRYABLE_MARKERS = TRANSIENT_MARKERS + (
    "sign in", "not a bot", "429", "too many requests", "403", "forbidden",
    "unable to extract", "http error 4", "po token",
    "requested format is not available", "login required", "rate-limit",
    "failed to extract any player",
)

TRANSIENT_RETRIES = 3        # attempts per configuration for transient errors
TRANSIENT_DELAY = 1.5        # seconds between those attempts


class DownloadError(Exception):
    """Raised with a user-friendly message when a download cannot complete."""


class Engine:
    def __init__(self, config: type[Config] = Config) -> None:
        self.config = config
        self.ffmpeg_location = find_ffmpeg(config.BASE_DIR)
        self._info_cache: dict[str, tuple[float, dict]] = {}
        self._cache_lock = threading.Lock()
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public status
    # ------------------------------------------------------------------ #
    @property
    def ffmpeg_available(self) -> bool:
        return self.ffmpeg_location is not None

    @property
    def cookies_available(self) -> bool:
        return os.path.isfile(self.config.COOKIES_FILE)

    @property
    def ytdlp_version(self) -> str:
        return yt_dlp.version.__version__

    # ------------------------------------------------------------------ #
    # Option building
    # ------------------------------------------------------------------ #
    def _base_options(self, extractor_args: ExtractorArgs = None, use_cookies: bool = False) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "noplaylist": True,
            "playlist_items": "1",
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 3,
            "socket_timeout": self.config.REQUEST_TIMEOUT,
            "sleep_interval_requests": 0.5,
            "concurrent_fragment_downloads": 4,
            "windowsfilenames": True,
            "http_headers": {"Accept-Language": "en-US,en;q=0.9"},
        }
        if extractor_args:
            opts["extractor_args"] = extractor_args
        if use_cookies and self.cookies_available:
            opts["cookiefile"] = self.config.COOKIES_FILE
        if self.config.PROXY:
            opts["proxy"] = self.config.PROXY
        if self.ffmpeg_location:  # empty string means "on PATH"
            opts["ffmpeg_location"] = self.ffmpeg_location
        return opts

    def _attempt_plan(self, platform: str) -> Iterator[tuple[ExtractorArgs, bool]]:
        """Yield (extractor_args, use_cookies) pairs in the order to try."""
        cookies = self.cookies_available
        if platform == "youtube":
            for variant in YOUTUBE_VARIANTS:
                yield variant, False
            if cookies:
                for variant in YOUTUBE_VARIANTS:
                    yield variant, True
        elif platform == "tiktok":
            for variant in TIKTOK_VARIANTS:
                yield variant, False
            if cookies:
                for variant in TIKTOK_VARIANTS:
                    yield variant, True
        elif platform in ("instagram", "facebook"):
            if cookies:
                yield None, True
            yield None, False
        else:
            yield None, False
            if cookies:
                yield None, True

    @staticmethod
    def _format_selector(platform: str, quality) -> str:
        """Build a yt-dlp format string: best video + best audio, no watermark."""
        no_watermark = "[format_note!*=?watermark]" if platform == "tiktok" else ""
        if quality == "audio":
            return "bestaudio/best"
        if quality == "best":
            return f"bv*{no_watermark}+ba/b{no_watermark}/b"
        h = int(quality)
        return (f"bv*[height<={h}]{no_watermark}+ba/"
                f"b[height<={h}]{no_watermark}/b{no_watermark}/b")

    @staticmethod
    def _matches(exc: BaseException, markers: tuple[str, ...]) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in markers)

    def _run_with_fallback(self, platform: str, action: Callable[[dict], object]):
        """
        Run ``action`` until it succeeds.

        For every configuration in the attempt plan, transient errors are retried
        a few times with a short delay. Blocking errors move on to the next
        configuration. Non-retryable errors stop immediately.
        """
        last_error: Optional[BaseException] = None
        for index, (extractor_args, use_cookies) in enumerate(self._attempt_plan(platform)):
            opts = self._base_options(extractor_args, use_cookies)
            for attempt in range(1, TRANSIENT_RETRIES + 1):
                try:
                    log.info("[%s] config %d try %d (args=%s, cookies=%s)",
                             platform, index + 1, attempt, extractor_args or "default", use_cookies)
                    return action(dict(opts))
                except Exception as exc:  # noqa: BLE001 - yt-dlp raises many types
                    last_error = exc
                    if self._matches(exc, TRANSIENT_MARKERS) and attempt < TRANSIENT_RETRIES:
                        log.warning("[%s] transient error, retrying: %s", platform, str(exc)[:120])
                        time.sleep(TRANSIENT_DELAY)
                        continue
                    break  # move to next configuration (or stop)
            if last_error is not None and not self._matches(last_error, RETRYABLE_MARKERS):
                break
            time.sleep(1 + index * 0.5)
        raise DownloadError(friendly_error(last_error or "Unknown error", platform))

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    @staticmethod
    def _select_entry(info: dict) -> tuple[dict, int]:
        """Return the first playable entry (handles carousels / playlists)."""
        entries = info.get("entries")
        if not entries:
            return info, 1
        entries = [e for e in list(entries) if e]
        videos = [e for e in entries if e.get("formats") or e.get("url")]
        if not videos:
            raise DownloadError("This post does not contain a video.")
        return videos[0], len(videos)

    def fetch_info(self, url: str) -> dict:
        platform = detect_platform(url)
        key = media_key(url, platform)

        with self._cache_lock:
            hit = self._info_cache.get(key)
        if hit and time.time() - hit[0] < self.config.INFO_CACHE_TTL:
            return hit[1]

        def action(opts: dict):
            with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as ydl:
                return ydl.extract_info(url, download=False)

        raw = self._run_with_fallback(platform, action)
        entry, count = self._select_entry(raw)

        heights = {
            f["height"] for f in entry.get("formats", [])
            if f.get("vcodec") not in (None, "none") and f.get("height")
        }
        info = {
            "platform": platform,
            "title": entry.get("title") or (entry.get("description") or "")[:100] or "Untitled video",
            "thumbnail": entry.get("thumbnail"),
            "duration": entry.get("duration"),
            "channel": entry.get("uploader") or entry.get("channel") or entry.get("uploader_id") or "",
            "views": entry.get("view_count"),
            "qualities": sorted(heights, reverse=True),
            "items": count,
        }
        with self._cache_lock:
            self._info_cache[key] = (time.time(), info)
        return info

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #
    def download(self, url: str, quality, on_progress: ProgressCallback) -> tuple[str, bool]:
        """
        Download ``url`` at ``quality``.

        Returns ``(file_path, from_cache)``.
        """
        if not self.ffmpeg_available:
            raise DownloadError(friendly_error("ffmpeg missing"))

        platform = detect_platform(url)
        folder = os.path.join(self.config.DOWNLOAD_DIR, platform,
                              media_key(url, platform), str(quality))
        os.makedirs(folder, exist_ok=True)

        cached = find_output_file(folder, quality)
        if cached and os.path.getsize(cached) > 0:
            log.info("[%s] cache hit -> %s", platform, os.path.basename(cached))
            return cached, True

        def progress_hook(d: dict) -> None:
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                on_progress(
                    status="downloading",
                    progress=round(done / total * 100, 1) if total else 0,
                    speed=human_speed(d.get("speed")),
                    eta=human_eta(d.get("eta")),
                )
            elif status == "finished":
                on_progress(status="merging", progress=100, speed="", eta="")

        def postprocessor_hook(d: dict) -> None:
            if d.get("status") == "started":
                on_progress(status="processing", progress=100, speed="", eta="")

        def action(opts: dict) -> None:
            opts.update({
                "outtmpl": os.path.join(folder, "%(title).80s [%(id)s].%(ext)s"),
                "format": self._format_selector(platform, quality),
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
                "continuedl": True,
                "overwrites": False,
            })
            if quality == "audio":
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
            else:
                opts["merge_output_format"] = "mp4"
                opts["postprocessors"] = [{
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",  # yt-dlp's own spelling
                }]
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        self._run_with_fallback(platform, action)

        result = find_output_file(folder, quality)
        if not result:
            raise DownloadError("The download finished but no output file was produced. Please try again.")
        return result, False


# Shared singleton used by the routes.
engine = Engine()