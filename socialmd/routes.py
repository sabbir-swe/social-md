"""HTTP routes: the single-page UI and the JSON API."""

from __future__ import annotations

import logging
import os
import threading
import urllib.request

from flask import Blueprint, Response, jsonify, render_template, request, send_file

from .config import Config
from .engine import DownloadError, engine
from .tasks import task_manager
from .utils import is_valid_url, parse_quality

log = logging.getLogger("socialmd.routes")

pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@pages.get("/")
def index():
    return render_template("index.html", app_name=Config.APP_NAME, version=Config.VERSION)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@api.get("/health")
def health():
    return jsonify({
        "app": Config.APP_NAME,
        "version": Config.VERSION,
        "ytdlp": engine.ytdlp_version,
        "ffmpeg": engine.ffmpeg_available,
        "cookies": engine.cookies_available,
    })


@api.post("/info")
def info():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not is_valid_url(url, Config.MAX_URL_LENGTH):
        return jsonify(error="Please enter a valid video URL."), 400
    try:
        return jsonify(engine.fetch_info(url))
    except DownloadError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:  # noqa: BLE001
        log.exception("Unexpected error while fetching info")
        return jsonify(error="Unexpected error while reading the video. Please try again."), 500


@api.post("/download")
def download():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not is_valid_url(url, Config.MAX_URL_LENGTH):
        return jsonify(error="Please enter a valid video URL."), 400
    try:
        quality = parse_quality(payload.get("quality", "best"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    task_id = task_manager.create()
    threading.Thread(target=_run_download, args=(task_id, url, quality), daemon=True).start()
    return jsonify(task_id=task_id), 202


@api.get("/progress/<task_id>")
def progress(task_id: str):
    task = task_manager.get(task_id)
    if task is None:
        return jsonify(status="error", error="Task not found."), 404
    task.pop("file", None)  # never expose server paths
    return jsonify(task)


@api.get("/file/<task_id>")
def file(task_id: str):
    task = task_manager.get(task_id)
    if not task or task.get("status") != "done" or not task.get("file"):
        return jsonify(error="File is not ready."), 404
    path = task["file"]
    if not os.path.isfile(path):
        return jsonify(error="File no longer exists on disk."), 410
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@api.get("/thumb")
def thumb():
    """Proxy thumbnails because some platforms block hot-linking."""
    url = request.args.get("u", "")
    if not url.startswith(("http://", "https://")):
        return "", 404
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(5 * 1024 * 1024)
            content_type = resp.headers.get("Content-Type", "image/jpeg")
        return Response(data, content_type=content_type,
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception:  # noqa: BLE001
        return "", 404


# --------------------------------------------------------------------------- #
# Background worker
# --------------------------------------------------------------------------- #
def _run_download(task_id: str, url: str, quality) -> None:
    def on_progress(**fields) -> None:
        task_manager.update(task_id, **fields)

    with task_manager.slot():
        task_manager.update(task_id, status="starting")
        try:
            path, from_cache = engine.download(url, quality, on_progress)
            task_manager.update(
                task_id, status="done", progress=100, speed="", eta="",
                file=path, filename=os.path.basename(path), cached=from_cache,
            )
        except DownloadError as exc:
            task_manager.update(task_id, status="error", error=str(exc))
        except Exception:  # noqa: BLE001
            log.exception("Unexpected error in download task %s", task_id)
            task_manager.update(task_id, status="error",
                                error="Unexpected error during download. Please try again.")