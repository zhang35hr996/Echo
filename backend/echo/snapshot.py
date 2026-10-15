import json
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.orm import Session
from echo.models import PlaylistSnapshot, PlaylistSnapshotItem, Alert, Track
from echo.registry import find_replacements


@dataclass
class SnapItem:
    source_track_id: str
    title_at_time: str = ""
    artist_at_time: str = ""
    position: int = 0
    available: bool = True
    unavailable_reason: str = ""  # transient, not persisted


@dataclass
class Renamed:
    source_track_id: str
    old_title: str
    new_title: str


@dataclass
class Changes:
    missing: list[SnapItem] = field(default_factory=list)
    added: list[SnapItem] = field(default_factory=list)
    renamed: list[Renamed] = field(default_factory=list)
    unavailable: list[SnapItem] = field(default_factory=list)
    recovered: list[SnapItem] = field(default_factory=list)


def diff(prev: list[SnapItem], cur: list[SnapItem]) -> Changes:
    prev_by_id = {i.source_track_id: i for i in prev}
    cur_by_id = {i.source_track_id: i for i in cur}
    ch = Changes()
    for vid, item in prev_by_id.items():
        if vid not in cur_by_id:
            ch.missing.append(item)
    for vid, item in cur_by_id.items():
        if vid not in prev_by_id:
            ch.added.append(item)
        elif prev_by_id[vid].title_at_time != item.title_at_time:
            ch.renamed.append(Renamed(vid, prev_by_id[vid].title_at_time, item.title_at_time))
        if vid in prev_by_id:
            if prev_by_id[vid].available and not item.available:
                ch.unavailable.append(item)
            elif not prev_by_id[vid].available and item.available:
                ch.recovered.append(item)
    ch.missing.sort(key=lambda i: i.source_track_id)
    ch.added.sort(key=lambda i: i.source_track_id)
    ch.renamed.sort(key=lambda r: r.source_track_id)
    ch.unavailable.sort(key=lambda i: i.source_track_id)
    ch.recovered.sort(key=lambda i: i.source_track_id)
    return ch


def capture(session: Session, playlist_id: str, fetched: list[SnapItem],
            ok: bool = True) -> PlaylistSnapshot:
    snap = PlaylistSnapshot(playlist_id=playlist_id, source="youtube", ok=ok)
    for it in fetched:
        snap.items.append(PlaylistSnapshotItem(
            source_track_id=it.source_track_id,
            title_at_time=it.title_at_time,
            artist_at_time=it.artist_at_time,
            position=it.position,
            available=it.available,
        ))
    session.add(snap)
    session.flush()
    return snap


def _latest_ok_snapshot(session: Session, playlist_id: str) -> PlaylistSnapshot | None:
    return session.scalar(
        select(PlaylistSnapshot)
        .where(PlaylistSnapshot.playlist_id == playlist_id, PlaylistSnapshot.ok == True)  # noqa: E712
        .order_by(PlaylistSnapshot.captured_at.desc())
    )


def _candidates(session: Session, item: SnapItem, search_fn) -> list[dict]:
    cands = [
        {"videoId": c.youtube_video_id, "title": c.title, "source": "registry"}
        for c in find_replacements(session, exclude_video_id=item.source_track_id,
                                   title=item.title_at_time, artist=item.artist_at_time,
                                   duration=0)
    ]
    if not cands and search_fn is not None:
        q = f"{item.title_at_time} {item.artist_at_time}".strip()
        cands = [{**c, "source": "youtube_search"} for c in search_fn(q)]
    return cands


def _track_for(session: Session, video_id: str) -> Track | None:
    return session.scalar(select(Track).where(Track.youtube_video_id == video_id))


def run_watchdog(session: Session, playlist_id: str, fetched: list[SnapItem],
                 search_fn=None) -> Changes:
    """Capture a new snapshot, diff against previous OK snapshot, raise alerts for
    missing and newly unavailable songs; restore tracks that became playable again."""
    prev_snap = _latest_ok_snapshot(session, playlist_id)
    prev_items = [SnapItem(i.source_track_id, i.title_at_time, i.artist_at_time,
                           i.position, i.available) for i in (prev_snap.items if prev_snap else [])]
    new_snap = capture(session, playlist_id, fetched, ok=True)
    changes = diff(prev_items, fetched)
    for kind, group in (("missing", changes.missing), ("unavailable", changes.unavailable)):
        for m in group:
            session.add(Alert(
                snapshot_id=new_snap.id, kind=kind, source_track_id=m.source_track_id,
                title_at_time=m.title_at_time, artist_at_time=m.artist_at_time,
                detail=m.unavailable_reason if kind == "unavailable" else "",
                candidate=json.dumps(_candidates(session, m, search_fn), ensure_ascii=False),
            ))
            track = _track_for(session, m.source_track_id)
            if track:
                track.status = kind
    # Playable again: either flipped back to available, or re-added to the playlist
    # after having gone missing. upsert_track() never resets status, so do it here.
    readded = [a for a in changes.added if a.available]
    for r in changes.recovered + readded:
        track = _track_for(session, r.source_track_id)
        if track and track.status in ("missing", "unavailable"):
            track.status = "active"
    return changes
