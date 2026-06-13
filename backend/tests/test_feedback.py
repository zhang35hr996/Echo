from datetime import datetime, timezone
from echo.models import Track, PlayEvent, TrackContextStats
from echo.feedback import record_event


def mk(session, vid):
    t = Track(youtube_video_id=vid, title="x", norm_title="x", norm_artist="")
    session.add(t); session.flush()
    return t


def test_record_updates_play_event_and_two_context_stats(session):
    t = mk(session, "v1")
    now = datetime(2026, 6, 13, 20, 0, tzinfo=timezone.utc)  # evening
    record_event(session, track_id=t.id, scene="coding", action="finish",
                 listened_seconds=180, duration_seconds=200, now=now)
    session.commit()
    assert session.query(PlayEvent).count() == 1
    # one stat row for scene 'coding', one for time bucket 'evening'
    keys = {s.context_key for s in session.query(TrackContextStats).all()}
    assert keys == {"coding", "evening"}
    scene_stat = session.query(TrackContextStats).filter_by(context_key="coding").one()
    assert scene_stat.play_count == 1
    assert abs(scene_stat.avg_completion - 0.9) < 1e-6


def test_manual_pick_and_skip_counts(session):
    t = mk(session, "v2")
    now = datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc)  # morning
    record_event(session, track_id=t.id, scene="driving", action="manual_pick",
                 listened_seconds=0, duration_seconds=200, now=now)
    record_event(session, track_id=t.id, scene="driving", action="skip",
                 listened_seconds=5, duration_seconds=200, now=now)
    session.commit()
    s = session.query(TrackContextStats).filter_by(context_key="driving").one()
    assert s.manual_pick_count == 1
    assert s.skip_count == 1
    assert s.play_count == 2  # both events count as a play occurrence
