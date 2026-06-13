from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Track(Base):
    __tablename__ = "tracks"
    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    artist: Mapped[str] = mapped_column(String, default="")
    album: Mapped[str | None] = mapped_column(String, default=None)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    norm_title: Mapped[str] = mapped_column(String, index=True, default="")
    norm_artist: Mapped[str] = mapped_column(String, index=True, default="")
    apple_music_id: Mapped[str | None] = mapped_column(String, default=None)
    local_file_path: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")  # active/missing/unavailable/duplicate
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TrackTag(Base):
    __tablename__ = "track_tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    tag_type: Mapped[str] = mapped_column(String)   # mood/scene/energy
    tag_value: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual/inferred/llm


class PlaylistSnapshot(Base):
    __tablename__ = "playlist_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, default="youtube")
    playlist_id: Mapped[str] = mapped_column(String, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)  # fetch fully succeeded
    items: Mapped[list["PlaylistSnapshotItem"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class PlaylistSnapshotItem(Base):
    __tablename__ = "playlist_snapshot_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("playlist_snapshots.id"), index=True)
    source_track_id: Mapped[str] = mapped_column(String, index=True)  # youtube video id
    title_at_time: Mapped[str] = mapped_column(String, default="")
    artist_at_time: Mapped[str] = mapped_column(String, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    snapshot: Mapped[PlaylistSnapshot] = relationship(back_populates="items")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("playlist_snapshots.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # missing/renamed/reupload
    source_track_id: Mapped[str] = mapped_column(String, index=True)
    title_at_time: Mapped[str] = mapped_column(String, default="")
    artist_at_time: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    candidate: Mapped[str] = mapped_column(Text, default="")  # JSON list of candidates
    resolution_status: Mapped[str] = mapped_column(String, default="open")  # open/resolved/unresolved
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlayEvent(Base):
    __tablename__ = "play_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    scene: Mapped[str] = mapped_column(String, default="")
    action: Mapped[str] = mapped_column(String)  # play/skip/replay/finish/manual_pick/too_noisy
    source: Mapped[str] = mapped_column(String, default="youtube")
    listened_seconds: Mapped[int] = mapped_column(Integer, default=0)
    completion_ratio: Mapped[float] = mapped_column(Float, default=0.0)


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    scene: Mapped[str] = mapped_column(String, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    candidate_track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)


class TrackContextStats(Base):
    __tablename__ = "track_context_stats"
    __table_args__ = (UniqueConstraint("track_id", "context_key", name="uq_track_context"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    context_key: Mapped[str] = mapped_column(String, index=True)  # scene name OR time bucket
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    manual_pick_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_completion: Mapped[float] = mapped_column(Float, default=0.0)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
