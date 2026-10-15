from echo.ingest.youtube import parse_playlist_items, parse_duration


def test_parse_duration_iso8601():
    assert parse_duration("PT3M20S") == 200
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("PT45S") == 45


def test_parse_playlist_items_maps_fields():
    raw = {
        "items": [
            {"snippet": {"resourceId": {"videoId": "v1"}, "title": "Title 1",
                          "videoOwnerChannelTitle": "Artist 1", "position": 0}},
            {"snippet": {"resourceId": {"videoId": "v2"}, "title": "Private video",
                          "position": 1}},
        ]
    }
    out = parse_playlist_items(raw)
    assert out[0].source_track_id == "v1"
    assert out[0].title_at_time == "Title 1"
    assert out[0].artist_at_time == "Artist 1"
    assert out[1].available is False  # "Private video" marker


# ---- availability ----
import echo.ingest.youtube as yt_mod
from echo.ingest.youtube import (
    parse_video_availability, get_video_availability, get_playlist_items,
    GLOBAL_BLOCK_THRESHOLD,
)


def vid(vid_id, status=None, region=None):
    it = {"id": vid_id, "status": status or {}, "contentDetails": {}}
    if region is not None:
        it["contentDetails"]["regionRestriction"] = region
    return it


def test_availability_not_found():
    out = parse_video_availability({"items": [vid("a")]}, ["a", "gone"])
    assert out == {"gone": "not_found"}


def test_availability_private():
    out = parse_video_availability({"items": [vid("a", {"privacyStatus": "private"})]}, ["a"])
    assert out == {"a": "private"}


def test_availability_upload_status():
    for st in ("rejected", "failed", "deleted"):
        out = parse_video_availability({"items": [vid("a", {"uploadStatus": st})]}, ["a"])
        assert out == {"a": f"upload_{st}"}
    assert parse_video_availability(
        {"items": [vid("a", {"uploadStatus": "processed"})]}, ["a"]) == {}


def test_availability_blocked_everywhere_by_long_list():
    blocked = [f"R{i}" for i in range(GLOBAL_BLOCK_THRESHOLD)]
    raw = {"items": [vid("a", {"privacyStatus": "unlisted"}, {"blocked": blocked})]}
    assert parse_video_availability(raw, ["a"]) == {"a": "blocked_everywhere"}


def test_availability_blocked_everywhere_by_empty_allowed():
    raw = {"items": [vid("a", region={"allowed": []})]}
    assert parse_video_availability(raw, ["a"]) == {"a": "blocked_everywhere"}


def test_availability_unlisted_alone_is_fine():
    raw = {"items": [vid("a", {"privacyStatus": "unlisted"})]}
    assert parse_video_availability(raw, ["a"], home_region="JP") == {}


def test_availability_short_blocked_list_without_home_region_is_fine():
    raw = {"items": [vid("a", region={"blocked": ["CN", "KP"]})]}
    assert parse_video_availability(raw, ["a"]) == {}


def test_availability_home_region_blocked_and_allowed():
    blocked = {"items": [vid("a", region={"blocked": ["JP"]})]}
    assert parse_video_availability(blocked, ["a"], home_region="jp") == {"a": "blocked_in_JP"}
    assert parse_video_availability(blocked, ["a"], home_region="US") == {}
    allowed = {"items": [vid("a", region={"allowed": ["US"]})]}
    assert parse_video_availability(allowed, ["a"], home_region="JP") == {"a": "blocked_in_JP"}
    assert parse_video_availability(allowed, ["a"], home_region="US") == {}


def test_availability_precedence():
    blocked = [f"R{i}" for i in range(GLOBAL_BLOCK_THRESHOLD)]
    raw = {"items": [
        vid("p", {"privacyStatus": "private", "uploadStatus": "rejected"},
            {"blocked": blocked}),
        vid("u", {"uploadStatus": "failed"}, {"blocked": blocked + ["JP"]}),
        vid("b", region={"blocked": blocked + ["JP"]}),
    ]}
    out = parse_video_availability(raw, ["p", "u", "b"], home_region="JP")
    assert out == {"p": "private", "u": "upload_failed", "b": "blocked_in_JP"}
    assert parse_video_availability(raw, ["b"]) == {"b": "blocked_everywhere"}


def test_availability_home_region_overrides_long_blocked_list():
    # Blocked in many regions but NOT at home: playable for the owner, so no flag.
    blocked = [f"R{i}" for i in range(GLOBAL_BLOCK_THRESHOLD)]
    raw = {"items": [vid("a", region={"blocked": blocked})]}
    assert parse_video_availability(raw, ["a"], home_region="JP") == {}
    assert parse_video_availability(raw, ["a"], home_region="R1") == {"a": "blocked_in_R1"}
    assert parse_video_availability(raw, ["a"]) == {"a": "blocked_everywhere"}
    # An explicit empty allow-list is authoritative regardless of home region.
    empty = {"items": [vid("a", region={"allowed": []})]}
    assert parse_video_availability(empty, ["a"], home_region="JP") == {"a": "blocked_everywhere"}


class _Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeYT:
    def __init__(self, pages, videos):
        self.pages = pages
        self.videos_resp = videos
        self.video_calls = []

    def playlistItems(self):
        outer = self

        class P:
            def list(self, **kw):
                return _Exec(lambda: outer.pages[kw.get("pageToken") or "first"])
        return P()

    def videos(self):
        outer = self

        class V:
            def list(self, **kw):
                outer.video_calls.append(kw)
                ids = kw["id"].split(",")
                return _Exec(lambda: {"items": [
                    v for v in outer.videos_resp if v["id"] in ids]})
        return V()


def _pl(vid_id, title="T"):
    return {"snippet": {"resourceId": {"videoId": vid_id}, "title": title,
                        "videoOwnerChannelTitle": "A", "position": 0}}


def test_get_playlist_items_marks_unavailable(monkeypatch):
    fake = FakeYT(
        {"first": {"items": [_pl("ok"), _pl("blk"), _pl("marker", "Private video")]}},
        [vid("ok"), vid("blk", {"privacyStatus": "unlisted"},
                        {"blocked": [f"R{i}" for i in range(GLOBAL_BLOCK_THRESHOLD)]})],
    )
    monkeypatch.setattr(yt_mod, "build", lambda *a, **k: fake)
    monkeypatch.setattr(yt_mod, "_credentials", lambda: object())
    items = {i.source_track_id: i for i in get_playlist_items("PL")}
    assert items["ok"].available is True and items["ok"].unavailable_reason == ""
    assert items["blk"].available is False
    assert items["blk"].unavailable_reason == "blocked_everywhere"
    assert items["marker"].available is False
    assert items["marker"].unavailable_reason == "title_marker"
    queried = [i for c in fake.video_calls for i in c["id"].split(",")]
    assert "marker" not in queried
    assert fake.video_calls[0]["part"] == "status,contentDetails"


def test_get_playlist_items_check_disabled(monkeypatch):
    fake = FakeYT({"first": {"items": [_pl("a")]}}, [])
    monkeypatch.setattr(yt_mod, "build", lambda *a, **k: fake)
    monkeypatch.setattr(yt_mod, "_credentials", lambda: object())
    get_playlist_items("PL", check_availability=False)
    assert fake.video_calls == []


def test_get_video_availability_batches_and_dedupes():
    ids = [f"v{i}" for i in range(120)] + ["v0", ""]
    fake = FakeYT({}, [])
    out = get_video_availability(ids, yt=fake)
    assert len(fake.video_calls) == 3
    assert all(len(c["id"].split(",")) <= 50 for c in fake.video_calls)
    assert len(out) == 120 and set(out.values()) == {"not_found"}
