"""Offline YouTube-like format lists, resolved by yt-dlp's real format selector.

The lists mirror what yt-dlp listed for a real 4K video in October 2026 (format
ids, codecs, containers, heights). URLs are placeholders: nothing here touches
the network or carries a token.
"""

from typing import Any

from yt_dlp import YoutubeDL

# Same sort fields the YouTube extractor attaches to every info dict.
_YOUTUBE_SORT_FIELDS = (
    "quality",
    "res",
    "fps",
    "hdr:12",
    "source",
    "vcodec",
    "channels",
    "acodec",
    "lang",
    "proto",
)


def fmt(
    format_id: str,
    ext: str,
    height: int | None,
    vcodec: str,
    acodec: str = "none",
    *,
    tbr: float = 1000,
    fps: int = 30,
    protocol: str = "https",
) -> dict[str, Any]:
    """Build one format entry."""
    return {
        "format_id": format_id,
        "ext": ext,
        "height": height,
        "width": height * 16 // 9 if height else None,
        "fps": fps if height else None,
        "vcodec": vcodec,
        "acodec": acodec,
        "tbr": tbr,
        "abr": tbr if vcodec == "none" else None,
        "protocol": protocol,
        "url": f"https://example.invalid/{format_id}",
    }


AUDIO = [
    fmt("140", "m4a", None, "none", "mp4a.40.2", tbr=129),
    fmt("251", "webm", None, "none", "opus", tbr=135),
]

# Signed-in web_safari style: pre-merged HLS only, nothing above 1080p.
HLS_ONLY_1080 = [
    fmt("93", "mp4", 360, "avc1.4D401E", "mp4a.40.2", tbr=700, protocol="m3u8_native"),
    fmt("95", "mp4", 720, "avc1.4D401F", "mp4a.40.2", tbr=2600, protocol="m3u8_native"),
    fmt(
        "96", "mp4", 1080, "avc1.640028", "mp4a.40.2", tbr=4600, protocol="m3u8_native"
    ),
]

# Full adaptive ladder where 1440p and 2160p exist only as VP9 in WebM.
VP9_ONLY_4K = [
    *AUDIO,
    fmt("18", "mp4", 360, "avc1.42001E", "mp4a.40.2", tbr=500),
    fmt("133", "mp4", 240, "avc1.4D4015", tbr=200),
    fmt("242", "webm", 240, "vp9", tbr=180),
    fmt("134", "mp4", 360, "avc1.4D401E", tbr=400),
    fmt("243", "webm", 360, "vp9", tbr=350),
    fmt("135", "mp4", 480, "avc1.4D401F", tbr=800),
    fmt("244", "webm", 480, "vp9", tbr=700),
    fmt("136", "mp4", 720, "avc1.4D401F", tbr=1500),
    fmt("247", "webm", 720, "vp9", tbr=1300),
    fmt("137", "mp4", 1080, "avc1.640028", tbr=4000),
    fmt("248", "webm", 1080, "vp9", tbr=2600),
    fmt("271", "webm", 1440, "vp9", tbr=9000),
    fmt("313", "webm", 2160, "vp9", tbr=18000),
]

# Same ladder plus AV1 in MP4 up to 2160p (what C3iHAgwIYtI offers signed out).
ADAPTIVE_4K = [
    *VP9_ONLY_4K,
    fmt("399", "mp4", 1080, "av01.0.08M.08", tbr=2200),
    fmt("400", "mp4", 1440, "av01.0.12M.08", tbr=7000),
    fmt("401", "mp4", 2160, "av01.0.12M.08", tbr=14000),
]


def select(spec: str, formats: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the processed info dict yt-dlp produces for ``spec`` over ``formats``."""
    info = {
        "id": "C3iHAgwIYtI",
        "title": "Fixture",
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://www.youtube.com/watch?v=C3iHAgwIYtI",
        "formats": [dict(f) for f in formats],
        "_format_sort_fields": _YOUTUBE_SORT_FIELDS,
    }
    with YoutubeDL({"format": spec, "simulate": True, "quiet": True}) as ydl:
        return ydl.process_ie_result(info, download=False)


def selected_ids(info: dict[str, Any]) -> list[str]:
    """Format ids yt-dlp chose, in merge order."""
    return [f["format_id"] for f in info.get("requested_formats") or [info]]
