import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from echo.config import settings
from echo.db import SessionLocal
from echo.ingest.youtube import get_playlist_items, search_videos
from echo.registry import upsert_track
from echo.snapshot import run_watchdog

log = logging.getLogger("echo.scheduler")


def run_daily_snapshot() -> None:
    if not settings.playlist_id:
        log.warning("ECHO_PLAYLIST_ID not set; skipping snapshot")
        return
    session = SessionLocal()
    try:
        fetched = get_playlist_items(settings.playlist_id)  # raises on API failure
        # keep registry in sync with currently-present items
        for it in fetched:
            if it.available and it.source_track_id:
                upsert_track(session, video_id=it.source_track_id,
                             title=it.title_at_time, artist=it.artist_at_time)
        changes = run_watchdog(session, settings.playlist_id, fetched, search_fn=search_videos)
        session.commit()
        log.info("snapshot ok: %d missing, %d added, %d renamed",
                 len(changes.missing), len(changes.added), len(changes.renamed))
    except Exception:
        session.rollback()
        log.exception("daily snapshot failed; previous snapshot retained")
    finally:
        session.close()


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(run_daily_snapshot,
                  CronTrigger(hour=settings.snapshot_hour, minute=0),
                  id="daily_snapshot", replace_existing=True)
    sched.start()
    return sched
