from echo.registry import upsert_track, find_replacements
from echo.models import Track


def test_upsert_creates_then_updates_by_video_id(session):
    t1 = upsert_track(session, video_id="abc123", title="Song A (Live)",
                      artist="Band - Topic", duration=200)
    session.commit()
    assert t1.id is not None
    assert t1.norm_title == "song a"
    assert t1.norm_artist == "band"

    t2 = upsert_track(session, video_id="abc123", title="Song A (Remaster)",
                      artist="Band", duration=205)
    session.commit()
    assert t2.id == t1.id  # same row updated, not duplicated
    assert session.query(Track).count() == 1


def test_find_replacements_matches_norm_title_and_duration(session):
    upsert_track(session, video_id="orig", title="Lost Song", artist="X", duration=180)
    upsert_track(session, video_id="reup", title="Lost Song (Reupload)", artist="X", duration=182)
    session.commit()
    cands = find_replacements(session, exclude_video_id="orig",
                              title="Lost Song", artist="X", duration=180)
    assert any(c.youtube_video_id == "reup" for c in cands)
    assert all(c.youtube_video_id != "orig" for c in cands)
