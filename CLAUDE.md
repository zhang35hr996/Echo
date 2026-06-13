# Echo — project context

Self-use music app: **library-safe + scene-aware recommendation queue** for one
person (the owner) who listens to a few-hundred-song YouTube Music playlist on
repeat. Solves two pains: (1) tedious song-hunting → scene queues; (2) songs
silently vanishing from the playlist → daily snapshot/diff watchdog with alerts.

## Why this shape

- **PWA + FastAPI/SQLite**, not a native app: the owner has **no Mac**, so SwiftUI
  is off the table. The PWA installs to the iPhone home screen; playback opens
  YouTube Music links (no embedded player).
- **Single process**: FastAPI serves the JSON API, the APScheduler daily job, and
  the PWA static files. SQLite is a single file. Free-tier Fly.io deploy.
- **No ML**: recommendation is a transparent additive weighted sum (see below),
  not a model. Easy to reason about and tune by hand.

## Layout

```
backend/echo/
  config.py        Settings (env prefix ECHO_). shared_token defaults "dev-token".
  models.py        SQLAlchemy 2.0 ORM. utcnow() is tz-AWARE; SQLite returns NAIVE.
  db.py            engine + SessionLocal + init_db()
  text_norm.py     normalize_title / normalize_artist (strip feat/brackets/-Topic)
  time_buckets.py  hour -> morning/afternoon/evening/night
  registry.py      upsert_track, find_replacements (norm_title + duration match)
  snapshot.py      SnapItem, diff(), capture(), run_watchdog()  ← disappeared-song core
  recommend.py     WEIGHTS, score_track(), build_queue()        ← queue core
  feedback.py      record_event() -> PlayEvent + 2 TrackContextStats rows
  ingest/youtube.py  OAuth client + pure parsers (parse_playlist_items/parse_duration)
  scheduler.py     APScheduler daily run_daily_snapshot()
  first_run.py     on-demand bootstrap (OAuth + first snapshot)
  api.py           FastAPI routes + static mount + startup
backend/web/       PWA: index.html, styles.css, app.js, sw.js, manifest
backend/tests/     pytest, in-memory SQLite `session` fixture in conftest.py
docs/superpowers/  specs/ (design) + plans/ (the 13-task TDD plan)
```

## Recommendation engine (recommend.py)

Scene-agnostic: a `scene` is just an opaque `context_key` string; per-scene and
per-time-bucket stats are learned in `TrackContextStats`. Score is additive:
`base_like + scene_match + time_match + completion + rediscovery − overplay −
skip + seed`, weighted by `WEIGHTS`.

**Scenes:** `drive` / `commute` / `work` (开车/上下班/工作) are learnable scenes.
**`rediscover` (听腻了·翻旧歌) is a special MODE, not a scene:** it uses
`REDISCOVER_WEIGHTS` (scene/time/seed → 0, rediscovery → 5.0) and ranks by
**global** staleness (max `last_played_at` across all contexts), surfacing
long-unplayed favorites. Logic branches on `scene == REDISCOVER_SCENE` in
`build_queue`.

## Conventions / gotchas

- **TDD throughout** (pytest). Run: `cd backend && .venv/bin/pytest -q`. Python is
  3.10 here (`.venv/bin/python`; no bare `python` on PATH).
- **tz-aware vs naive datetimes**: `utcnow()` is aware, SQLite round-trips to
  naive → subtracting them raises `TypeError`. `recommend.py` has a `_normalize`
  guard for this; watch for the same trap anywhere you subtract a stored datetime.
- **Watchdog never false-flags on API failure**: `run_daily_snapshot` only diffs
  after a fully successful fetch; on error it rolls back and keeps the last
  snapshot. Disappeared detection needs a *previous* snapshot to diff against.
- **Secrets stay gitignored**: `client_secret*.json`, `token.json`, `.env`,
  `*.db`. `shared_token` is a simple single-user access guard sent as
  `X-Echo-Token`, not real auth.
- Two harmless test warnings: Google-lib Python-3.10 FutureWarning and FastAPI
  `@app.on_event` deprecation.

## Status

MVP complete (plan Tasks 1–13, all merged to `main`). Owner-side manual steps
before live use: Google Cloud OAuth setup, set `ECHO_PLAYLIST_ID`, run
`python -m echo.first_run`, then `fly deploy`. See README.
