from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from echo.config import settings
from echo.db import SessionLocal, init_db
from echo.models import Track, Alert
from echo.recommend import build_queue
from echo.feedback import record_event
from echo.time_buckets import time_bucket

app = FastAPI(title="Echo")


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def require_token(x_echo_token: str = Header(default="")):
    if x_echo_token != settings.shared_token:
        raise HTTPException(status_code=401, detail="bad token")


class FeedbackIn(BaseModel):
    youtube_video_id: str
    scene: str
    action: str
    listened_seconds: int = 0
    duration_seconds: int = 0


def _track_json(t: Track) -> dict:
    return {"id": t.id, "youtube_video_id": t.youtube_video_id, "title": t.title,
            "artist": t.artist, "duration_seconds": t.duration_seconds,
            "yt_music_url": f"https://music.youtube.com/watch?v={t.youtube_video_id}"}


@app.get("/api/queue", dependencies=[Depends(require_token)])
def queue(scene: str = Query(...), seed_video_id: str | None = None,
          session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    seed_id = None
    if seed_video_id:
        seed = session.scalar(select(Track).where(Track.youtube_video_id == seed_video_id))
        seed_id = seed.id if seed else None
    tracks = build_queue(session, scene=scene, time_ctx=time_bucket(now.hour),
                         now=now, limit=20, seed_track_id=seed_id)
    return {"scene": scene, "queue": [_track_json(t) for t in tracks]}


@app.get("/api/alerts", dependencies=[Depends(require_token)])
def alerts(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Alert).where(Alert.resolution_status == "open").order_by(Alert.detected_at.desc())
    ).all()
    return [{"id": a.id, "kind": a.kind, "source_track_id": a.source_track_id,
             "title_at_time": a.title_at_time, "candidate": a.candidate,
             "detected_at": a.detected_at.isoformat()} for a in rows]


@app.post("/api/feedback", dependencies=[Depends(require_token)])
def feedback(body: FeedbackIn, session: Session = Depends(get_session)):
    track = session.scalar(select(Track).where(Track.youtube_video_id == body.youtube_video_id))
    if track is None:
        raise HTTPException(status_code=404, detail="track not found")
    record_event(session, track_id=track.id, scene=body.scene, action=body.action,
                 listened_seconds=body.listened_seconds,
                 duration_seconds=body.duration_seconds, now=datetime.now(timezone.utc))
    session.commit()
    return {"ok": True}


@app.post("/api/alerts/{alert_id}/resolve", dependencies=[Depends(require_token)])
def resolve(alert_id: int, status: str = Query("resolved"),
            session: Session = Depends(get_session)):
    a = session.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail="alert not found")
    a.resolution_status = status
    session.commit()
    return {"ok": True}


_scheduler = None


@app.on_event("startup")
def _startup():
    global _scheduler
    init_db()
    from echo.scheduler import start_scheduler
    _scheduler = start_scheduler()


# Serve the PWA. Mounted last so /api/* takes precedence.
_web = Path(settings.web_dir)
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
