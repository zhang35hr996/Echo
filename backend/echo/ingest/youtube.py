# echo/ingest/youtube.py
import re
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from echo.config import settings
from echo.snapshot import SnapItem

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
_UNAVAILABLE_TITLES = {"Private video", "Deleted video", "[Private video]", "[Deleted video]"}
GLOBAL_BLOCK_THRESHOLD = 240  # YouTube has ~249 region codes; this many blocked == worldwide
_BAD_UPLOAD = {"rejected", "failed", "deleted"}
_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_duration(iso: str) -> int:
    m = _DUR.fullmatch(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def parse_playlist_items(raw: dict) -> list[SnapItem]:
    out = []
    for it in raw.get("items", []):
        sn = it["snippet"]
        vid = sn.get("resourceId", {}).get("videoId", "")
        title = sn.get("title", "")
        out.append(SnapItem(
            source_track_id=vid,
            title_at_time=title,
            artist_at_time=sn.get("videoOwnerChannelTitle", ""),
            position=sn.get("position", 0),
            available=title not in _UNAVAILABLE_TITLES,
        ))
    return out


def _credentials() -> Credentials:
    creds = None
    try:
        creds = Credentials.from_authorized_user_file(settings.token_file, SCOPES)
    except (FileNotFoundError, ValueError):
        creds = None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(settings.client_secret_file, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(settings.token_file, "w") as f:
            f.write(creds.to_json())
    return creds


def parse_video_availability(raw: dict, requested_ids: list[str],
                             home_region: str = "") -> dict[str, str]:
    """Map video_id -> reason for ids that are unplayable. Pure function."""
    home = (home_region or "").upper()
    found = {it.get("id"): it for it in raw.get("items", [])}
    out: dict[str, str] = {}
    for vid in requested_ids:
        it = found.get(vid)
        if it is None:
            out[vid] = "not_found"
            continue
        status = it.get("status", {})
        rr = it.get("contentDetails", {}).get("regionRestriction") or {}
        blocked = rr.get("blocked")
        allowed = rr.get("allowed")
        if status.get("privacyStatus") == "private":
            out[vid] = "private"
        elif status.get("uploadStatus") in _BAD_UPLOAD:
            out[vid] = f"upload_{status['uploadStatus']}"
        elif (allowed is not None and len(allowed) == 0) or \
                len(blocked or []) >= GLOBAL_BLOCK_THRESHOLD:
            out[vid] = "blocked_everywhere"
        elif home and (home in (blocked or []) or (allowed and home not in allowed)):
            out[vid] = f"blocked_in_{home}"
    return out


def get_video_availability(video_ids: list[str], yt=None) -> dict[str, str]:
    """Return {video_id: reason} for unplayable ids. Raises on API failure."""
    ids = list(dict.fromkeys(v for v in video_ids if v))
    if not ids:
        return {}
    yt = yt or build("youtube", "v3", credentials=_credentials())
    out: dict[str, str] = {}
    for k in range(0, len(ids), 50):
        batch = ids[k:k + 50]
        resp = yt.videos().list(part="status,contentDetails", id=",".join(batch),
                                maxResults=50).execute()
        out.update(parse_video_availability(resp, batch, home_region=settings.home_region))
    return out


def get_playlist_items(playlist_id: str, check_availability: bool = True) -> list[SnapItem]:
    """Fetch all items of a playlist. Raises on API failure (caller handles)."""
    yt = build("youtube", "v3", credentials=_credentials())
    items: list[SnapItem] = []
    page_token = None
    while True:
        resp = yt.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=50, pageToken=page_token
        ).execute()
        items.extend(parse_playlist_items(resp))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    for it in items:
        if not it.available and not it.unavailable_reason:
            it.unavailable_reason = "title_marker"
    if check_availability:
        by_id = {it.source_track_id: it for it in items
                 if it.available and it.source_track_id}
        for vid, reason in get_video_availability(list(by_id), yt=yt).items():
            by_id[vid].available = False
            by_id[vid].unavailable_reason = reason
    return items


def search_videos(query: str, max_results: int = 3) -> list[dict]:
    """Search YouTube for replacement candidates. Returns [{videoId,title,channel}]."""
    yt = build("youtube", "v3", credentials=_credentials())
    resp = yt.search().list(part="snippet", q=query, type="video",
                            maxResults=max_results).execute()
    return [
        {"videoId": it["id"]["videoId"], "title": it["snippet"]["title"],
         "channel": it["snippet"].get("channelTitle", "")}
        for it in resp.get("items", [])
    ]
