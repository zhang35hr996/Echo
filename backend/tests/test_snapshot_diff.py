from echo.snapshot import diff, SnapItem, capture, run_watchdog
from echo.models import PlaylistSnapshot, Alert, Track
from echo.registry import upsert_track


def items(*specs):
    # specs: (video_id, title, position)
    return [SnapItem(source_track_id=v, title_at_time=t, artist_at_time="", position=p)
            for (v, t, p) in specs]


def test_diff_detects_missing_added_renamed():
    prev = items(("a", "Alpha", 0), ("b", "Beta", 1), ("c", "Gamma", 2))
    cur = items(("a", "Alpha", 0), ("c", "Gamma (Live)", 1), ("d", "Delta", 2))
    ch = diff(prev, cur)
    assert [m.source_track_id for m in ch.missing] == ["b"]
    assert [a.source_track_id for a in ch.added] == ["d"]
    assert [(r.source_track_id, r.old_title, r.new_title) for r in ch.renamed] == [
        ("c", "Gamma", "Gamma (Live)")
    ]


def test_diff_empty_prev_means_all_added_no_missing():
    cur = items(("a", "Alpha", 0))
    ch = diff([], cur)
    assert ch.missing == []
    assert [a.source_track_id for a in ch.added] == ["a"]


def fake_fetch_factory(items_list):
    calls = {"n": 0}
    def _fetch(playlist_id):
        items_list_local = items_list[calls["n"]]
        calls["n"] += 1
        return items_list_local
    return _fetch


def test_capture_persists_snapshot_and_items(session):
    snap = capture(session, "PL1", items(("a", "Alpha", 0), ("b", "Beta", 1)))
    session.commit()
    assert session.query(PlaylistSnapshot).count() == 1
    assert len(snap.items) == 2


def test_watchdog_flags_missing_and_creates_alert(session):
    # registry has a reupload candidate for the soon-missing song
    upsert_track(session, video_id="b-reup", title="Beta", artist="", duration=0)
    capture(session, "PL1", items(("a", "Alpha", 0), ("b", "Beta", 1)))
    session.commit()
    # second capture: 'b' is gone
    changes = run_watchdog(session, "PL1", items(("a", "Alpha", 0)),
                           search_fn=lambda q, max_results=3: [])
    session.commit()
    assert [m.source_track_id for m in changes.missing] == ["b"]
    alerts = session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].kind == "missing"
    assert alerts[0].source_track_id == "b"
    # candidate from registry (norm_title match) recorded
    assert "b-reup" in alerts[0].candidate


def _item(v, available=True, reason="", title="T"):
    return SnapItem(source_track_id=v, title_at_time=title, available=available,
                    unavailable_reason=reason)


def test_diff_detects_unavailable_and_recovered():
    prev = [_item("a"), _item("b", False, "x"), _item("c", False), _item("d")]
    cur = [_item("a", False, "private"), _item("b"), _item("c", False), _item("d", title="T2")]
    ch = diff(prev, cur)
    assert [i.source_track_id for i in ch.unavailable] == ["a"]
    assert [i.source_track_id for i in ch.recovered] == ["b"]
    assert ch.missing == [] and ch.added == []
    assert [r.source_track_id for r in ch.renamed] == ["d"]


def test_watchdog_unavailable_alert_and_track_status(session):
    upsert_track(session, video_id="a", title="Alpha", artist="")
    upsert_track(session, video_id="a-reup", title="Alpha", artist="")
    capture(session, "PL1", [_item("a", title="Alpha")])
    session.commit()
    changes = run_watchdog(session, "PL1",
                           [_item("a", False, "blocked_everywhere", title="Alpha")],
                           search_fn=lambda q, max_results=3: [])
    session.commit()
    assert [i.source_track_id for i in changes.unavailable] == ["a"]
    alerts = session.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].kind == "unavailable"
    assert alerts[0].detail == "blocked_everywhere"
    assert alerts[0].source_track_id == "a"
    assert "a-reup" in alerts[0].candidate
    assert session.query(Track).filter_by(youtube_video_id="a").one().status == "unavailable"


def test_watchdog_recovery_restores_status_no_alert(session):
    upsert_track(session, video_id="a", title="Alpha", artist="")
    capture(session, "PL1", [_item("a", False, "private", title="Alpha")])
    session.query(Track).filter_by(youtube_video_id="a").one().status = "unavailable"
    session.commit()
    changes = run_watchdog(session, "PL1", [_item("a", title="Alpha")])
    session.commit()
    assert [i.source_track_id for i in changes.recovered] == ["a"]
    assert session.query(Alert).count() == 0
    assert session.query(Track).filter_by(youtube_video_id="a").one().status == "active"


def test_watchdog_unavailable_in_both_snapshots_is_silent(session):
    capture(session, "PL1", [_item("a", False, "private")])
    session.commit()
    changes = run_watchdog(session, "PL1", [_item("a", False, "private")])
    session.commit()
    assert changes.unavailable == [] and changes.recovered == []
    assert session.query(Alert).count() == 0
