import re

_BRACKETS = re.compile(r"[\(\[].*?[\)\]]")
_FEAT = re.compile(r"\b(feat|ft|featuring)\.?\b.*", re.IGNORECASE)
_NONWORD = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    s = title or ""
    s = _BRACKETS.sub(" ", s)
    s = _FEAT.sub(" ", s)
    s = _NONWORD.sub(" ", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def normalize_artist(artist: str) -> str:
    s = artist or ""
    s = re.sub(r"\s*-\s*topic\s*$", "", s, flags=re.IGNORECASE)
    s = _NONWORD.sub(" ", s)
    s = _WS.sub(" ", s).strip().lower()
    return s
