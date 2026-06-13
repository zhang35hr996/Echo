from sqlalchemy import select
from sqlalchemy.orm import Session
from echo.models import Track
from echo.text_norm import normalize_title, normalize_artist

DURATION_TOLERANCE = 8  # seconds


def upsert_track(session: Session, *, video_id: str, title: str,
                 artist: str = "", duration: int = 0) -> Track:
    track = session.scalar(select(Track).where(Track.youtube_video_id == video_id))
    if track is None:
        track = Track(youtube_video_id=video_id)
        session.add(track)
    track.title = title
    track.artist = artist
    track.duration_seconds = duration
    track.norm_title = normalize_title(title)
    track.norm_artist = normalize_artist(artist)
    return track


def find_replacements(session: Session, *, exclude_video_id: str, title: str,
                      artist: str, duration: int) -> list[Track]:
    nt, na = normalize_title(title), normalize_artist(artist)
    rows = session.scalars(
        select(Track).where(Track.norm_title == nt,
                            Track.youtube_video_id != exclude_video_id)
    ).all()
    out = []
    for r in rows:
        if na and r.norm_artist and r.norm_artist != na:
            continue
        if duration and r.duration_seconds and abs(r.duration_seconds - duration) > DURATION_TOLERANCE:
            continue
        out.append(r)
    return out
