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


def get_playlist_items(playlist_id: str) -> list[SnapItem]:
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
