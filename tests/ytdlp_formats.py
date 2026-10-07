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
    language: str | None = None,
    language_preference: int = -1,
    quality: float | None = None,
    source_preference: int = -1,
    dynamic_range: str = "SDR",
) -> dict[str, Any]:
    """Build one format entry."""
    return {
        "source_preference": source_preference,
        "dynamic_range": dynamic_range if height else None,
        "language": language,
        "language_preference": language_preference,
        "quality": quality,
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


# Original-language AAC, Opus and E-AC-3 surround, YouTube's "stable volume"
# (DRC) copy of the AAC (a separate encode, so its bitrate differs slightly),
# and a higher-bitrate dubbed track.
AUDIO_TRACKS = [
    fmt(
        "140",
        "m4a",
        None,
        "none",
        "mp4a.40.2",
        tbr=129.47,
        language="en",
        language_preference=10,
        quality=2,
    ),
    fmt(
        "140-drc",
        "m4a",
        None,
        "none",
        "mp4a.40.2",
        tbr=129.52,
        language="en",
        language_preference=10,
        quality=1.5,
    ),
    fmt(
        "251",
        "webm",
        None,
        "none",
        "opus",
        tbr=135,
        language="en",
        language_preference=10,
        quality=2,
    ),
    fmt(
        "140-fr",
        "m4a",
        None,
        "none",
        "mp4a.40.2",
        tbr=160,
        language="fr",
        language_preference=-1,
        quality=2,
    ),
]

AUDIO_TRACKS.append(
    fmt(
        "328",
        "m4a",
        None,
        "none",
        "ec-3",
        tbr=384,
        language="en",
        language_preference=10,
        quality=2,
    )
)

# kC179N-Fx_s signed in (October 2026): AV1 is the lowest-bitrate stream at
# every height, yet yt-dlp's default codec order picks it.
FOUR_K_SIGNED_IN = [
    *AUDIO_TRACKS,
    fmt("399", "mp4", 1080, "av01.0.08M.08", tbr=561, fps=25),
    fmt("248", "webm", 1080, "vp9", tbr=1031, fps=25),
    fmt("137", "mp4", 1080, "avc1.640028", tbr=1687, fps=25),
    fmt("400", "mp4", 1440, "av01.0.12M.08", tbr=1452, fps=25),
    fmt("271", "webm", 1440, "vp9", tbr=2991, fps=25),
    fmt("401", "mp4", 2160, "av01.0.12M.08", tbr=2952, fps=25),
    fmt("313", "webm", 2160, "vp9", tbr=8763, fps=25),
]

# Signed out adds visionos HLS streams: VP9 in MP4 at far higher bitrates.
FOUR_K_SIGNED_OUT = [
    *FOUR_K_SIGNED_IN,
    fmt("614", "mp4", 1080, "vp09.00.40.08", tbr=2414, fps=25, protocol="m3u8_native"),
    fmt("270", "mp4", 1080, "avc1.640028", tbr=4322, fps=25, protocol="m3u8_native"),
    fmt("620", "mp4", 1440, "vp09.00.50.08", tbr=6803, fps=25, protocol="m3u8_native"),
    fmt("625", "mp4", 2160, "vp09.00.50.08", tbr=23495, fps=25, protocol="m3u8_native"),
]

# UE-Ij-ymt5o tops out at 1080p50. The 25fps stream is not in the real list:
# it checks that a higher frame rate beats a higher bitrate.
HFR_1080 = [
    *AUDIO_TRACKS,
    fmt("399", "mp4", 1080, "av01.0.09M.08", tbr=1236, fps=50),
    fmt("303", "webm", 1080, "vp9", tbr=1707, fps=50),
    fmt("299", "mp4", 1080, "avc1.64002A", tbr=2667, fps=50),
    fmt("312", "mp4", 1080, "avc1.64002A", tbr=3469, fps=50, protocol="m3u8_native"),
    fmt("617", "mp4", 1080, "vp09.00.41.08", tbr=3757, fps=50, protocol="m3u8_native"),
    fmt("137", "mp4", 1080, "avc1.640028", tbr=9999, fps=25),
]

# An 8K upload: AV1 in MP4 and VP9 in WebM at 4320p on top of the 4K ladder.
EIGHT_K = [
    *FOUR_K_SIGNED_IN,
    fmt("571", "mp4", 4320, "av01.0.16M.08", tbr=21000, fps=25),
    fmt("272", "webm", 4320, "vp9", tbr=26000, fps=25),
]


# A YouTube Premium session: 616 is the enhanced-bitrate 1080p, served over
# HLS (source_preference +100 in yt-dlp, -1 for everything else).
PREMIUM_1080 = [
    *AUDIO_TRACKS,
    fmt("399", "mp4", 1080, "av01.0.08M.08", tbr=1200),
    fmt("248", "webm", 1080, "vp9", tbr=2000),
    fmt("137", "mp4", 1080, "avc1.640028", tbr=2600),
    fmt(
        "616",
        "mp4",
        1080,
        "vp09.00.40.08",
        tbr=5000,
        protocol="m3u8_native",
        source_preference=99,
    ),
]

# 4K with both SDR and HDR10 encodes; the SDR VP9 has the highest bitrate.
HDR_4K = [
    *AUDIO_TRACKS,
    fmt("401", "mp4", 2160, "av01.0.12M.08", tbr=2952),
    fmt("313", "webm", 2160, "vp9", tbr=8763),
    fmt("701", "mp4", 2160, "av01.0.13M.10", tbr=6000, dynamic_range="HDR10"),
    fmt("337", "webm", 2160, "vp9.2", tbr=7500, dynamic_range="HDR10"),
]


def select(
    spec: str,
    formats: list[dict[str, Any]],
    format_sort: tuple[str, ...] | None = None,
    merge_output_format: str | None = None,
) -> dict[str, Any]:
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
    params: dict[str, Any] = {"format": spec, "simulate": True, "quiet": True}
    if format_sort:
        params["format_sort"] = list(format_sort)
    if merge_output_format:
        params["merge_output_format"] = merge_output_format
    with YoutubeDL(params) as ydl:
        return ydl.process_ie_result(info, download=False)


def selected_ids(info: dict[str, Any]) -> list[str]:
    """Format ids yt-dlp chose, in merge order."""
    return [f["format_id"] for f in info.get("requested_formats") or [info]]
