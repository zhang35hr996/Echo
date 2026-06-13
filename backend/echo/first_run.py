"""One-shot bootstrap: authorize YouTube OAuth and capture the first snapshot.

Run from ``backend/`` after placing ``client_secret.json`` and choosing a
playlist:

    ECHO_PLAYLIST_ID=PLxxxx python -m echo.first_run

On first run a browser window opens for YouTube authorization; the resulting
``token.json`` is reused afterwards. This does exactly what the daily scheduler
job does, but on demand, so you can verify real data flows into the PWA without
waiting for the cron trigger.
"""
import logging

from sqlalchemy import func, select

from echo.config import settings
from echo.db import SessionLocal, init_db
from echo.models import Alert, PlaylistSnapshot, Track
from echo.scheduler import run_daily_snapshot


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not settings.playlist_id:
        raise SystemExit(
            "ECHO_PLAYLIST_ID is not set. Run with:\n"
            "    ECHO_PLAYLIST_ID=PLxxxx python -m echo.first_run"
        )

    init_db()
    print(f"Capturing first snapshot of playlist {settings.playlist_id} ...")
    print("(A browser window will open for YouTube authorization on first run.)")
    run_daily_snapshot()  # logs its own ok/failure summary; never raises

    with SessionLocal() as s:
        snapshots = s.scalar(select(func.count()).select_from(PlaylistSnapshot))
        tracks = s.scalar(select(func.count()).select_from(Track))
        open_alerts = s.scalar(
            select(func.count()).select_from(Alert).where(Alert.resolution_status == "open")
        )
    print(f"\nDone. db={settings.db_path}  snapshots={snapshots}  "
          f"tracks={tracks}  open_alerts={open_alerts}")
    if snapshots == 0:
        print("No snapshot was stored — check the log above (OAuth / API error?).")


if __name__ == "__main__":
    main()
