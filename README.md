# Echo

Self-use music "library safe + scene recommendation queue". Backend snapshots a
YouTube playlist daily to catch disappeared songs; an installable PWA serves a
scene-aware listening queue and logs feedback. Playback opens YouTube Music.

See `docs/superpowers/specs/2026-06-13-echo-design.md` for the design and
`docs/superpowers/plans/2026-06-13-echo-mvp.md` for the build plan.

## Local dev

    cd backend
    python -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"
    pytest
    ECHO_SHARED_TOKEN=dev-token ECHO_PLAYLIST_ID=PLxxxx uvicorn echo.api:app --reload

Open http://localhost:8000, enter the token, pick a scene.

## YouTube OAuth (one time)

1. Google Cloud Console → enable **YouTube Data API v3**.
2. Create an OAuth **Desktop** client, download `client_secret.json` into `backend/`.
3. First run of the snapshot opens a browser to authorize; `token.json` is saved.

## First run (authorize + load real data)

After `client_secret.json` is in `backend/`, capture the first snapshot on
demand instead of waiting for the daily 04:00 UTC job:

    cd backend
    . .venv/bin/activate
    ECHO_PLAYLIST_ID=PLxxxx python -m echo.first_run

A browser opens for YouTube authorization (saving `token.json`), the playlist is
read into the canonical track registry, and a baseline snapshot is stored. It
prints a `snapshots / tracks / open_alerts` summary. Start the server and the
PWA scene queues now have real songs. (The first run reports `open_alerts=0` —
disappeared-song detection needs a *previous* snapshot to diff against, which the
next daily job provides.)

## Deploy (Fly.io)

    cd backend
    fly launch --no-deploy        # uses fly.toml
    fly volumes create echo_data --size 1
    fly secrets set ECHO_SHARED_TOKEN=<your-strong-token> ECHO_PLAYLIST_ID=<playlist-id>
    fly deploy

Upload `client_secret.json`/`token.json` to the `/data` volume (e.g. via
`fly ssh console` + `fly ssh sftp shell`) so OAuth persists.

## Config (env, prefix `ECHO_`)

| Var | Default | Meaning |
|---|---|---|
| `ECHO_SHARED_TOKEN` | `dev-token` | access guard sent as `X-Echo-Token` |
| `ECHO_PLAYLIST_ID` | (empty) | YouTube playlist to watch |
| `ECHO_DB_PATH` | `echo.db` | SQLite file |
| `ECHO_SNAPSHOT_HOUR` | `4` | daily snapshot hour (UTC) |
