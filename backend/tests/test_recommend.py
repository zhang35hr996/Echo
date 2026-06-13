from datetime import timedelta
from echo.models import Track, TrackContextStats, utcnow
from echo.recommend import build_queue, score_track, WEIGHTS


def mk_track(session, vid, title="t", status="active"):
    t = Track(youtube_video_id=vid, title=title, status=status,
              norm_title=title, norm_artist="")
    session.add(t)
    session.flush()
    return t


def add_stat(session, track, ctx, **kw):
    s = TrackContextStats(track_id=track.id, context_key=ctx, **kw)
    session.add(s)
    session.flush()
    return s


def test_scene_match_ranks_higher(session):
    liked = mk_track(session, "liked")
    plain = mk_track(session, "plain")
    add_stat(session, liked, "coding", play_count=5, manual_pick_count=3,
             avg_completion=0.9, last_played_at=utcnow() - timedelta(days=30))
    add_stat(session, plain, "coding", play_count=0, last_played_at=None)
    session.commit()
    queue = build_queue(session, scene="coding", time_ctx="night", now=utcnow(), limit=10)
    assert queue[0].youtube_video_id == "liked"


def test_skipped_track_penalized(session):
    a = mk_track(session, "a")
    b = mk_track(session, "b")
    add_stat(session, a, "coding", play_count=2, skip_count=5,
             last_played_at=utcnow() - timedelta(days=30))
    add_stat(session, b, "coding", play_count=2, skip_count=0,
             last_played_at=utcnow() - timedelta(days=30))
    session.commit()
    queue = build_queue(session, scene="coding", time_ctx="night", now=utcnow(), limit=10)
    assert queue.index(next(t for t in queue if t.youtube_video_id == "b")) < \
           queue.index(next(t for t in queue if t.youtube_video_id == "a"))


def test_overplayed_recently_penalized(session):
    fresh = mk_track(session, "fresh")
    stale = mk_track(session, "stale")
    add_stat(session, fresh, "coding", play_count=3,
             last_played_at=utcnow() - timedelta(hours=2))   # just played -> overplay penalty
    add_stat(session, stale, "coding", play_count=3,
             last_played_at=utcnow() - timedelta(days=20))    # rediscovery bonus
    session.commit()
    queue = build_queue(session, scene="coding", time_ctx="night", now=utcnow(), limit=10)
    assert queue[0].youtube_video_id == "stale"


def test_missing_tracks_excluded(session):
    mk_track(session, "gone", status="missing")
    mk_track(session, "ok")
    session.commit()
    queue = build_queue(session, scene="coding", time_ctx="night", now=utcnow(), limit=10)
    assert all(t.youtube_video_id != "gone" for t in queue)


def test_rediscover_mode_surfaces_stale_over_recent(session):
    fresh = mk_track(session, "fresh")
    stale = mk_track(session, "stale")
    # Both are well-liked in the same scene; only staleness differs.
    add_stat(session, fresh, "work", play_count=5, manual_pick_count=3,
             avg_completion=0.9, last_played_at=utcnow() - timedelta(hours=3))
    add_stat(session, stale, "work", play_count=5, manual_pick_count=3,
             avg_completion=0.9, last_played_at=utcnow() - timedelta(days=40))
    session.commit()
    queue = build_queue(session, scene="rediscover", time_ctx="night", now=utcnow(), limit=10)
    assert queue[0].youtube_video_id == "stale"
