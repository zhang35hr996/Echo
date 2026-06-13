import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from echo.models import Base, Track, Alert
import echo.api as api


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, future=True)
    def session_override():
        yield from _yield(TestSession)
    api.app.dependency_overrides[api.get_session] = session_override
    with TestSession() as s:
        s.add(Track(youtube_video_id="v1", title="Song", norm_title="song", norm_artist=""))
        s.add(Alert(snapshot_id=1, kind="missing", source_track_id="gone",
                    title_at_time="Gone Song", candidate="[]"))
        s.commit()
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def _yield(TestSession):
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


HEADERS = {"X-Echo-Token": "dev-token"}


def test_auth_required(client):
    assert client.get("/api/queue?scene=coding").status_code == 401


def test_queue_returns_tracks(client):
    r = client.get("/api/queue?scene=coding", headers=HEADERS)
    assert r.status_code == 200
    assert any(t["youtube_video_id"] == "v1" for t in r.json()["queue"])


def test_alerts_lists_open_missing(client):
    r = client.get("/api/alerts", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()[0]["source_track_id"] == "gone"


def test_feedback_records(client):
    r = client.post("/api/feedback", headers=HEADERS, json={
        "youtube_video_id": "v1", "scene": "coding", "action": "finish",
        "listened_seconds": 180, "duration_seconds": 200})
    assert r.status_code == 200
    assert r.json()["ok"] is True
