from echo.snapshot import diff, SnapItem


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
