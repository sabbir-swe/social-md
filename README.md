# SOCIAL-MD

A clean, fast, self-hosted video downloader for **YouTube, TikTok, Instagram and Facebook**.
Paste a link, pick a quality (144p → 4K or MP3), and get the original file — audio included, no watermark.

## Features

- Automatic platform detection from the URL
- Real available qualities per video (no fake options)
- Best video + best audio merged into a single MP4, or MP3 extraction
- TikTok downloads without watermark
- Smart fallback across player clients / cookies when a request is blocked
- Local cache: the same video is served instantly on repeat downloads
- Live progress with speed and ETA, download history, keyboard shortcuts
- Runs 100% on your machine — nothing is uploaded anywhere

## Requirements

| Tool    | Why                                   | Install (Windows)                   |
|---------|---------------------------------------|-------------------------------------|
| Python 3.10+ | Runs the app                     | https://www.python.org/downloads/   |
| FFmpeg  | Merges video + audio, creates MP3     | `winget install --id Gyan.FFmpeg -e` |

> You may also drop `ffmpeg.exe` next to `run.py` / `SOCIAL-MD.exe` instead of installing it.

## Quick start

```bash
pip install -r requirements.txt
python run.py
```

Windows users can simply double-click `run.bat`. The browser opens at http://127.0.0.1:5000.

## Project structure

```
SOCIAL-MD/
├── run.py              Entry point (starts server, opens browser)
├── socialmd/           Backend package
│   ├── config.py       Settings & path resolution (dev + PyInstaller)
│   ├── engine.py       yt-dlp engine, fallback strategy, caching
│   ├── tasks.py        Thread-safe background task registry
│   ├── routes.py       Page + JSON API routes
│   └── utils.py        Helpers (platform detection, formatting, errors)
├── templates/          HTML
├── static/             CSS, JS, icons
└── downloads/          Output files (grouped by platform / id / quality)
```

## API

| Method | Endpoint              | Description                        |
|--------|-----------------------|------------------------------------|
| GET    | `/api/health`         | Versions and FFmpeg / cookies state |
| POST   | `/api/info`           | `{ url }` → metadata + qualities   |
| POST   | `/api/download`       | `{ url, quality }` → `{ task_id }` |
| GET    | `/api/progress/<id>`  | Task status / progress             |
| GET    | `/api/file/<id>`      | Download the finished file         |

## Private / login-only content (Instagram, Facebook, some YouTube)

1. Install the browser extension **"Get cookies.txt LOCALLY"**.
2. While logged in, export cookies for the site(s) you need.
3. Save the file as `cookies.txt` next to `run.py` (or the `.exe`).

The app automatically uses it as a fallback. Keep this file private — it grants access to your account.

## Building a Windows executable

```bat
build.bat
```

The result is `dist/SOCIAL-MD.exe`. Ship it together with `ffmpeg.exe` in the same folder.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Sign in to confirm you're not a bot" | `pip install -U yt-dlp`, add `cookies.txt`, disable VPN |
| Instagram / Facebook errors | Add `cookies.txt` (see above) |
| "FFmpeg was not found" | Install FFmpeg or place `ffmpeg.exe` next to the app |
| Downloads suddenly stop working | Platforms change often — update: `pip install -U yt-dlp` |

## Legal

This tool is for downloading content you own or are permitted to save for personal, offline use.
Respect each platform's terms of service and creators' rights.