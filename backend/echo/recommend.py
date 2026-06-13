from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from echo.models import Track, TrackContextStats, TrackTag

WEIGHTS = {
    "base_like": 1.0,
    "scene": 2.0,
    "time": 1.0,
    "completion": 1.5,
    "rediscovery": 1.0,
    "overplay": -2.0,
    "skip": -0.75,
    "seed": 3.0,
}

# "听腻了" mode: surface long-unplayed favorites. Scene/time/seed matching is
# dropped; staleness dominates and recently-played tracks are pushed down.
REDISCOVER_WEIGHTS = {**WEIGHTS, "scene": 0.0, "time": 0.0, "seed": 0.0,
                      "rediscovery": 5.0}
REDISCOVER_SCENE = "rediscover"


def _normalize(now: datetime, last: datetime) -> datetime:
    """Return now with tzinfo stripped when last is naive (SQLite stores naive datetimes)."""
    if last.tzinfo is None and now.tzinfo is not None:
        return now.replace(tzinfo=None)
    return now


def _rediscovery(now: datetime, last) -> float:
    if last is None:
        return 0.5
    now = _normalize(now, last)
    days = (now - last).days
    if days >= 14:
        return 1.0
    if days >= 7:
        return 0.5
    return 0.0


def _overplay(now: datetime, last) -> float:
    if last is None:
        return 0.0
    now = _normalize(now, last)
    hours = (now - last).total_seconds() / 3600.0
    if hours < 24:
        return 1.0
    if hours < 48:
        return 0.5
    return 0.0


def score_track(now: datetime, scene_stat, time_stat, global_agg, seed_match: float,
                weights: dict | None = None) -> float:
    w = weights or WEIGHTS
    s = scene_stat
    tb = time_stat
    base_like = 0.5 * global_agg["manual_pick"] + 1.0 * global_agg["avg_completion"]
    scene_match = 1.0 * s["manual_pick"] + 0.5 * s["play"] - 1.0 * s["skip"]
    time_match = 0.5 * tb["play"] - 0.5 * tb["skip"]
    completion = s["avg_completion"]
    redis = _rediscovery(now, s["last"])
    over = _overplay(now, s["last"])
    skip_pen = s["skip"]
    return (
        w["base_like"] * base_like
        + w["scene"] * scene_match
        + w["time"] * time_match
        + w["completion"] * completion
        + w["rediscovery"] * redis
        + w["overplay"] * over
        + w["skip"] * skip_pen
        + w["seed"] * seed_match
    )


def _empty_stat():
    return {"play": 0, "skip": 0, "manual_pick": 0, "avg_completion": 0.0, "last": None}


def _stat_to_dict(st: TrackContextStats):
    return {"play": st.play_count, "skip": st.skip_count,
            "manual_pick": st.manual_pick_count, "avg_completion": st.avg_completion,
            "last": st.last_played_at}


def build_queue(session: Session, *, scene: str, time_ctx: str, now: datetime,
                limit: int = 20, seed_track_id: int | None = None) -> list[Track]:
    tracks = session.scalars(select(Track).where(Track.status == "active")).all()
    stats = session.scalars(select(TrackContextStats)).all()
    by_track: dict[int, dict[str, dict]] = {}
    agg: dict[int, dict] = {}
    for st in stats:
        by_track.setdefault(st.track_id, {})[st.context_key] = _stat_to_dict(st)
        a = agg.setdefault(st.track_id, {"manual_pick": 0, "avg_completion": 0.0, "n": 0})
        a["manual_pick"] += st.manual_pick_count
        a["avg_completion"] += st.avg_completion
        a["n"] += 1

    seed_tags = set()
    if seed_track_id is not None:
        seed_tags = {
            (t.tag_type, t.tag_value)
            for t in session.scalars(select(TrackTag).where(TrackTag.track_id == seed_track_id))
        }

    is_rediscover = scene == REDISCOVER_SCENE
    weights = REDISCOVER_WEIGHTS if is_rediscover else WEIGHTS

    scored = []
    for t in tracks:
        ctxs = by_track.get(t.id, {})
        if is_rediscover:
            # Rank by global staleness across every context, not a single scene.
            global_last = max((c["last"] for c in ctxs.values() if c["last"]), default=None)
            scene_stat = {**_empty_stat(), "last": global_last}
        else:
            scene_stat = ctxs.get(scene, _empty_stat())
        time_stat = ctxs.get(time_ctx, _empty_stat())
        a = agg.get(t.id, {"manual_pick": 0, "avg_completion": 0.0, "n": 0})
        global_agg = {"manual_pick": a["manual_pick"],
                      "avg_completion": (a["avg_completion"] / a["n"]) if a["n"] else 0.0}
        seed_match = 0.0
        if seed_tags and t.id != seed_track_id:
            t_tags = {(tg.tag_type, tg.tag_value)
                      for tg in session.scalars(select(TrackTag).where(TrackTag.track_id == t.id))}
            if seed_tags & t_tags:
                seed_match = 1.0
        scored.append((score_track(now, scene_stat, time_stat, global_agg, seed_match, weights), t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:limit]]
