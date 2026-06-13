from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from echo.models import PlayEvent, TrackContextStats
from echo.time_buckets import time_bucket

_SKIP_ACTIONS = {"skip", "too_noisy"}
_MANUAL_ACTIONS = {"manual_pick"}


def _upsert_stat(session: Session, track_id: int, ctx: str, completion: float,
                 action: str, now: datetime) -> None:
    st = session.scalar(
        select(TrackContextStats).where(
            TrackContextStats.track_id == track_id, TrackContextStats.context_key == ctx)
    )
    if st is None:
        st = TrackContextStats(track_id=track_id, context_key=ctx)
        session.add(st)
        st.play_count = 0
        st.skip_count = 0
        st.manual_pick_count = 0
        st.avg_completion = 0.0
    # running average of completion over play occurrences
    n = st.play_count
    st.avg_completion = (st.avg_completion * n + completion) / (n + 1)
    st.play_count = n + 1
    if action in _SKIP_ACTIONS:
        st.skip_count += 1
    if action in _MANUAL_ACTIONS:
        st.manual_pick_count += 1
    st.last_played_at = now


def record_event(session: Session, *, track_id: int, scene: str, action: str,
                 listened_seconds: int, duration_seconds: int, now: datetime,
                 source: str = "youtube") -> PlayEvent:
    completion = (listened_seconds / duration_seconds) if duration_seconds else 0.0
    completion = max(0.0, min(1.0, completion))
    ev = PlayEvent(track_id=track_id, played_at=now, scene=scene, action=action,
                   source=source, listened_seconds=listened_seconds,
                   completion_ratio=completion)
    session.add(ev)
    _upsert_stat(session, track_id, scene, completion, action, now)
    _upsert_stat(session, track_id, time_bucket(now.hour), completion, action, now)
    return ev
