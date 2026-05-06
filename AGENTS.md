# AGENTS.md

Guidance for Codex and other AI coding agents working in this repository.

## Project Shape

- Python Discord music bot entrypoint: `bot.py`
- Slash command cogs: `cogs/`
- Runtime services: `services/`
- Music domain layer: `services/music/`
- Dashboard frontend: `dash-ui/`
- Localization files: `locales/`
- Unit tests: `tests/`

## Required Checks

Run these before reporting backend or full-stack changes as complete:

```powershell
python -m py_compile bot.py config.py generate_cert.py
python -m compileall cogs/ services/ tests/ -q
python -m unittest discover -s tests -v
```

Run these before reporting dashboard changes as complete:

```powershell
Set-Location dash-ui
npm run lint
npm run build
```

## Development Rules

- Keep Discord command startup sync behavior intact unless the user explicitly asks to change it.
- Keep `DASHBOARD_BIND` defaulting to `0.0.0.0` unless the user explicitly asks to change it.
- Keep dashboard reversible password storage and `password_display` behavior unless the user explicitly asks to remove it.
- Do not introduce broad refactors when a small service-level fix is enough.
- Prefer `unittest` for Python tests unless the project intentionally adopts another test framework.
- Avoid live Discord, Spotify, YouTube, SoundCloud, or Genius calls in tests; mock network-facing boundaries.
- Do not commit generated runtime files such as `.env`, certs, SQLite databases, dashboard `dist/`, or cache files.

## Important Runtime Notes

- `MusicPlayer` owns a background playback task. Cleanup must go through `PlayerManager.cleanup()` or `MusicPlayer.close()`.
- New music code should prefer the domain layer in `services/music/`:
  - `queue.py` for queue data structures and saved queue serialization
  - `playback.py` for playback state and audio filter registry
  - `policies.py` for DJ/admin/requester control checks
  - `ui.py` for player panel/component helpers
  - `session.py` for higher-level session facades
- `DashboardServer` shares the bot database connection and should not create a separate SQLite connection.
- The dashboard trusts forwarded IP headers only when `TRUSTED_PROXY_IPS` is configured.
- `yt-dlp` and Genius calls run in dedicated thread pools and have shutdown hooks called from `MusicBot.shutdown_resources()`.

## Useful Commands

```powershell
# Inspect changed files
git status --short

# Run all Python tests
python -m unittest discover -s tests -v

# Build dashboard
Set-Location dash-ui
npm run build
```
