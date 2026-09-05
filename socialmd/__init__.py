"""SOCIAL-MD - a clean multi-platform video downloader."""

from flask import Flask

from .config import Config
from .routes import api, pages

__version__ = Config.VERSION


def create_app() -> Flask:
    """Application factory."""
    app = Flask(
        __name__,
        template_folder=Config.TEMPLATE_DIR,
        static_folder=Config.STATIC_DIR,
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # JSON bodies only
    app.register_blueprint(pages)
    app.register_blueprint(api, url_prefix="/api")
    return app