# Testing Guide

This project uses Python `unittest` for backend coverage and the dashboard's existing npm scripts for frontend validation.

## Backend

```powershell
python -m py_compile bot.py config.py generate_cert.py
python -m compileall cogs/ services/ tests/ -q
python -m unittest discover -s tests -v
```

Current test coverage focuses on deterministic project logic:

- music helper formatting and title cleanup
- slash-command control guard behavior
- player shutdown and voice cleanup behavior
- music domain queue/filter/component-id behavior
- saved queue database persistence
- extractor platform detection and TTL cache behavior
- lyrics TTL cache behavior
- SQLite database CRUD behavior
- dashboard login limiter and trusted-proxy IP handling

Live Discord voice playback and external media APIs are intentionally not hit by unit tests.

## Dashboard

```powershell
Set-Location dash-ui
npm run lint
npm run build
```

## Adding Tests

- Put backend tests in `tests/test_*.py`.
- Use `unittest.TestCase` or `unittest.IsolatedAsyncioTestCase`.
- Mock Discord objects with small fakes or `types.SimpleNamespace`.
- Mock yt-dlp, Spotify, SoundCloud, YouTube, Genius, and Discord network boundaries.
- Keep tests independent from `.env` and local SQLite files by using temporary files.
