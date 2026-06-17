# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Employee monitoring demo system with three components:

```
Agent (Python, Windows) → Server (FastAPI, Docker) → Dashboard (browser)
```

- **Agent**: Runs on monitored machines. Captures screenshots, tracks active windows, collects browser history, monitors Enter key in chat apps.
- **Server**: Receives and stores data via REST API. Serves a web dashboard.
- **Dashboard**: Vue 3 + Vite + Pinia (`server/dashboard/`), Raycast 风格深色主题。构建产物输出到 `server/static/dist/`。备用: `server/static/dashboard-v0-raycast.html`（旧版单文件）。

All Chinese comments and UI text. Communication with the user should be in Chinese — they are a non-technical product manager who describes requirements in everyday language.

## Commands

### Server (Docker)

```bash
cd server
docker compose up -d          # Build & start → http://localhost:8899
docker compose logs -f        # View logs
docker compose down           # Stop
```

### Server (local dev)

```bash
cd server
pip install -r requirements.txt
python main.py                # Starts uvicorn on :8899
# API docs at http://localhost:8899/docs
```

### Agent (from source)

```bash
cd agent
pip install -r requirements.txt
python main.py                # Requires Windows + monitor server reachable
```

### Dashboard (frontend)

```bash
cd server/dashboard
npm install                # Install dependencies
npm run dev                # Vite dev server (http://localhost:5173) with API proxy
npm run build              # Build to server/static/dist/
```

### Agent (build .exe)

```bash
cd agent
build.bat                     # PyInstaller → dist/monitor-agent.exe
```

### No tests exist yet. The `tests/` directory is empty.

## Architecture

### Data flow

Agent captures data on a timer → HTTP POST to Server API → SQLite DB + filesystem for screenshots → Dashboard polls API for display.

Key timing: Agent's screenshot frequency adapts based on user activity (4 levels: active 0.25s → very deep idle 600s). When someone is watching the Dashboard, the browser sends a viewer heartbeat every second to `/api/viewer/heartbeat`. The server tracks active viewers; if any viewer is present, the agent's `/api/config` endpoint signals it to switch to 1s "LIVE" mode. Agent polls `/api/config` every 3 seconds to pick up the signal.

### Server structure

| File | Role |
|------|------|
| `server/main.py` | FastAPI app, lifespan, CORS, security headers, static file mount |
| `server/routes.py` | All REST endpoints (`/api/*`), ~25 routes on an `APIRouter` |
| `server/models.py` | SQLite data layer — schema DDL in `init_db()`, all CRUD functions, thread-local connections with WAL mode |
| `server/config.py` | Env-var driven config (host, port, data dir, CORS) |
| `server/logger.py` | File + console logging with daily rotation |

### Dashboard structure (Vue 3 + Vite)

| Directory | Role |
|-----------|------|
| `server/dashboard/src/main.js` | Vue app entry — createApp + Pinia |
| `server/dashboard/src/App.vue` | Shell — backdrop + 4-pane grid + overlays |
| `server/dashboard/src/api.js` | All API calls (fetch wrapper) |
| `server/dashboard/src/stores/` | Pinia stores: agent, screenshot, theme |
| `server/dashboard/src/composables/` | usePolling (heartbeat + refresh), useConfirm |
| `server/dashboard/src/components/` | 12 Vue components (see below) |
| `server/dashboard/src/styles/` | tokens.css (design tokens), global.css |
| `server/dashboard/vite.config.js` | base: `/static/dist/`, proxy `/api` to :8899 |

Components: `AppHeader`, `AgentStrip`, `ScreenshotCard`, `ScreenshotViewer`, `LiveOverlay`, `GridOverlay`, `TimelineCard`, `BrowserCard`, `LogCard`, `StatsBar`, `ThemePicker`, `ConfirmDialog`

### Agent structure

| File | Role |
|------|------|
| `agent/main.py` | Orchestrator — starts all collectors, manages Reporter, adaptive frequency controller |
| `agent/config.py` | All config via env vars, platform detection, browser paths, chat app whitelist |
| `agent/screen_capture.py` | Multi-monitor screenshot capture (PIL ImageGrab + Win32 EnumDisplayMonitors) |
| `agent/app_tracker.py` | Active window tracking (win32gui on Windows, xdotool on Linux) |
| `agent/browser_history.py` | Chrome/Edge/Firefox history DB reading |
| `agent/keyboard_monitor.py` | Enter key detection in whitelisted chat apps (pynput, producer-consumer with bounded queue) |

### Database (SQLite, 5 tables)

- `agents` — agent registry with online/offline status
- `screenshots` — index only; actual images stored as files under `data/screenshots/{agent}/{date}/`
- `app_events` — window switches + chat Enter events, linked to screenshots by timestamp
- `browser_history` — deduped by (agent, url, last_visit)
- `diagnostic_logs` — agent-reported errors + server-side logs

Schema migrations: done inline in `init_db()` via `ALTER TABLE ... ADD COLUMN` with `try/except` for idempotency. No migration framework.

### Screenshot-event correlation

App events and browser history records are matched to screenshots by timestamp proximity. The matching logic is in `get_app_events_with_screenshots()` and `get_browser_history_with_screenshots()` in `models.py` — uses COALESCE with 3-tier fallback (exact → after → before).

## Key Patterns

- **No ORM**: All SQL is raw `sqlite3` with `?` placeholders. Thread-local connections via `threading.local()`.
- **Config separation**: Agent and Server each have their own `config.py`. Never mix them.
- **Agent is stateless on disk**: All persistence is on the server. Agent only keeps runtime state in memory.
- **Retry with diagnostic reporting**: Agent retries failed uploads 3 times, then reports the failure to the server's `/api/diagnostics` endpoint (never writes local logs).
- **Screenshot throttle**: Server-side 2-second window throttle per monitor — if a screenshot already exists in the 2s window for the same monitor, the new one is skipped and the earliest is kept (`ORDER BY timestamp ASC LIMIT 1`).

## Key Environment Variables

**Agent** (`agent/config.py`):
- `MONITOR_SERVER_HOST` / `MONITOR_SERVER_PORT` — server address (default: `192.168.61.133:8899`)
- `AGENT_NAME` — display name (default: `试验机-01`)
- `SCREENSHOT_INTERVAL` / `APP_TRACK_INTERVAL` / `BROWSER_HISTORY_INTERVAL` — collection intervals in seconds
- `KEYBOARD_MONITOR_ENABLED` — set to `false` to disable Enter key monitoring
- `HEARTBEAT_INTERVAL` — agent heartbeat to server (default: 15s)

**Server** (`server/config.py`):
- `SERVER_HOST` / `SERVER_PORT` — listen address (default: `0.0.0.0:8899`)
- `DATA_DIR` — storage root for SQLite DB and screenshots (default: `server/data/`)
- `CORS_ORIGINS` — comma-separated allowed origins (default: `*`)

## Critical Notes

- **Data sensitivity**: System captures screenshots, keyboard Enter events, and browser history. All data-handling changes need security review.
- **Cross-platform**: Agent uses `pywin32` (Windows-only). Server runs in Docker (Linux). Code must respect `IS_WINDOWS`/`IS_LINUX` flags in `agent/config.py`.
- **PyInstaller**: `agent/agent.spec` defines the .exe build. New Python dependencies must be added to `_HIDDEN_IMPORTS` in the spec file.
- **Dashboard is one file**: `server/static/dashboard.html` contains all frontend code. No build step, no npm, no framework.
