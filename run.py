"""Entry point: start the local server and open the browser."""

import logging
import threading
import webbrowser

from socialmd import create_app
from socialmd.config import Config
from socialmd.engine import engine


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def print_banner(url: str) -> None:
    ffmpeg = "OK" if engine.ffmpeg_available else "MISSING (720p+ and MP3 will fail)"
    cookies = "found" if engine.cookies_available else "not found (optional)"
    print(f"""
  {Config.APP_NAME} v{Config.VERSION}
  ----------------------------------------------
  URL        : {url}
  yt-dlp     : {engine.ytdlp_version}
  FFmpeg     : {ffmpeg}
  cookies.txt: {cookies}
  Downloads  : {Config.DOWNLOAD_DIR}
  ----------------------------------------------
  Close this window to stop the server.
""")


def main() -> None:
    configure_logging()
    url = f"http://{Config.HOST}:{Config.PORT}"
    app = create_app()
    print_banner(url)
    if Config.OPEN_BROWSER:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()