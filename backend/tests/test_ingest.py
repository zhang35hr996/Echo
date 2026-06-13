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
