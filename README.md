# EZ_qbitsox

Flask dashboard for fetching SOCKS5 proxies, running multi-step health tests, and applying a selected proxy to qBittorrent Web UI.

## What It Does

- Pulls proxy candidates from multiple remote source lists.
- Normalizes and deduplicates proxy entries.
- Runs layered validation:
  - TCP connect
  - SOCKS5 handshake
  - Remote connect
  - DNS test
  - HTTP/HTTPS checks through SOCKS5
  - Optional bandwidth/tracker checks
- Displays sortable results in a browser UI.
- Applies selected proxy to qBittorrent via Web API.
- Supports periodic background refresh/retest with scheduler.

## Security Changes (Current Update)

- Removed hardcoded qBittorrent credentials from code defaults.
- `.env-sample` now uses `CHANGE_ME` placeholders.
- Added comprehensive `.gitignore` rules for:
  - secrets (`.env*`)
  - generated caches/results
  - backups, screenshots, wheels, build outputs

## Requirements

- Python 3.8+
- qBittorrent with Web UI enabled
- See [requirements.txt](/PiDrive/_Functional Tools/EZ_qbitsox/requirements.txt)

Install:

```bash
pip install -r requirements.txt
```

## Configuration

1. Copy sample env:

```bash
cp .env-sample .env
```

2. Edit `.env` with your actual qBittorrent credentials:

```env
QBITTORRENT_HOST=localhost
QBITTORRENT_PORT=7070
QBITTORRENT_USERNAME=your_username
QBITTORRENT_PASSWORD=your_password
```

3. Edit [sources.txt](/PiDrive/_Functional Tools/EZ_qbitsox/sources.txt) (one proxy-list URL per line).

## Run

```bash
python app.py
```

Open:

`http://localhost:4141`

## Project Layout

- [app.py](/PiDrive/_Functional Tools/EZ_qbitsox/app.py): Flask routes and app orchestration
- [proxy_manager.py](/PiDrive/_Functional Tools/EZ_qbitsox/proxy_manager.py): proxy fetch/test/cache logic
- [qbittorrent_manager.py](/PiDrive/_Functional Tools/EZ_qbitsox/qbittorrent_manager.py): qBittorrent API auth and proxy apply
- [scheduler.py](/PiDrive/_Functional Tools/EZ_qbitsox/scheduler.py): periodic background jobs
- [templates/index.html](/PiDrive/_Functional Tools/EZ_qbitsox/templates/index.html): UI template
- [static/js/script.js](/PiDrive/_Functional Tools/EZ_qbitsox/static/js/script.js): front-end behavior
- [static/css/style.css](/PiDrive/_Functional Tools/EZ_qbitsox/static/css/style.css): styling

## Operational Notes

- Keep `.env` local and private.
- Do not commit generated proxy result files.
- Validate source URLs periodically; public proxy feeds change frequently.
- Many public proxies are unstable; repeated failures are expected.

## Troubleshooting

- `Missing qBittorrent credentials`:
  - Ensure `.env` exists and has `QBITTORRENT_USERNAME` / `QBITTORRENT_PASSWORD`.
- qBittorrent connection/auth failures:
  - Verify host/port and Web UI credentials.
  - Confirm Web UI is enabled in qBittorrent.
- No proxies displayed:
  - Check source URL availability.
  - Check network access and logs.

## License

MIT (see [LICENSE](/PiDrive/_Functional Tools/EZ_qbitsox/LICENSE) if present in your branch/repo context).
