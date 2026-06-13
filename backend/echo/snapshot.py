from dataclasses import dataclass, field


@dataclass
class SnapItem:
    source_track_id: str
    title_at_time: str = ""
    artist_at_time: str = ""
    position: int = 0
    available: bool = True


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
    ch.missing.sort(key=lambda i: i.source_track_id)
    ch.added.sort(key=lambda i: i.source_track_id)
    ch.renamed.sort(key=lambda r: r.source_track_id)
    return ch
