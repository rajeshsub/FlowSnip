"""
Configuration management for FlowSnip.

Handles loading, saving, and validation of application settings using Pydantic.
Supports both file-based configuration and command-line overrides.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

CUSTOM_VIDEO_QUALITY = "Custom"


def _capped_preset(height: int, fallback_to_best: bool) -> str:
    """Highest stream at or below ``height``, whatever its codec or container."""
    spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
    return f"{spec}/best" if fallback_to_best else spec


# Resolution decides first; VIDEO_FORMAT_SORT picks among streams of equal
# resolution. Filtering on container (e.g. [ext=mp4]) ahead of resolution
# silently capped VP9-only 4K and 1440p uploads at 1080p.
VIDEO_QUALITY_PRESETS: Mapping[str, str] = MappingProxyType(
    {
        "Best Quality": "bestvideo+bestaudio/best",
        "8K (4320p)": _capped_preset(4320, fallback_to_best=True),
        "4K (2160p)": _capped_preset(2160, fallback_to_best=True),
        "1440p": _capped_preset(1440, fallback_to_best=True),
        "1080p": _capped_preset(1080, fallback_to_best=True),
        "720p": _capped_preset(720, fallback_to_best=False),
        "480p": _capped_preset(480, fallback_to_best=False),
        "360p": _capped_preset(360, fallback_to_best=False),
        "240p": _capped_preset(240, fallback_to_best=False),
    }
)


def _legacy_mp4_first_preset(height: int, fallback_to_best: bool) -> str:
    """Preset strings shipped up to v0.1.4, still present in saved configs."""
    mp4_first = (
        f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo[height<={height}]+bestaudio"
    )
    if fallback_to_best:
        return f"{mp4_first}/best[ext=mp4]/best"
    return f"{mp4_first}/best[ext=mp4][height<={height}]/best[height<={height}]"


_LEGACY_VIDEO_QUALITY: dict[str, str] = {
    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best": (
        VIDEO_QUALITY_PRESETS["Best Quality"]
    ),
    **{
        _legacy_mp4_first_preset(height, fallback): VIDEO_QUALITY_PRESETS[name]
        for name, height, fallback in (
            ("8K (4320p)", 4320, True),
            ("4K (2160p)", 2160, True),
            ("1440p", 1440, True),
            ("1080p", 1080, True),
            ("720p", 720, False),
            ("480p", 480, False),
            ("360p", 360, False),
            ("240p", 240, False),
        )
    },
}


# How yt-dlp ranks streams for preset video downloads, most important first:
#   lang        original-language audio, before any dub
#   res, fps    highest resolution, then frame rate
#   hdr:12      HDR over SDR when both exist (yt-dlp's own default)
#   acodec:aac  stereo AAC over Opus and E-AC-3: native to MP4 and playable
#               everywhere (browsers can't decode E-AC-3)
#   source      YouTube Premium's enhanced-bitrate streams over regular ones
#   proto       direct (https) streams over HLS, whose listed bitrates are
#               peaks: an HLS VP9 stream listed at 3.8 Mbps was the same
#               1.7 Mbps encode as its DASH twin
#   quality     YouTube's quality class, which ranks DRC audio below normal
#   br          then the highest bitrate, whatever the codec
# yt-dlp's default ranks codec (AV1 > VP9 > H.264) above bitrate, which picks
# YouTube's AV1 encode even when it is a fraction of the VP9 or H.264 bitrate
# at the same resolution and visibly worse.
VIDEO_FORMAT_SORT: tuple[str, ...] = (
    "lang",
    "res",
    "fps",
    "hdr:12",
    "acodec:aac",
    "source",
    "proto",
    "quality",
    "br",
)

# Merged preset video downloads are saved as MP4; VP9 and AV1 are copied in
# as-is. A single pre-merged stream keeps its own container.
VIDEO_CONTAINER = "mp4"


def video_quality_display_name(format_string: str) -> str:
    """Return the preset name for a format string, or "Custom" if none matches."""
    for name, preset in VIDEO_QUALITY_PRESETS.items():
        if preset == format_string:
            return name
    return CUSTOM_VIDEO_QUALITY


class DownloadConfig(BaseModel):
    """Configuration for download behavior."""

    max_parallel_downloads: int = Field(default=3, ge=1, le=10)
    download_directory: Path = Field(default=Path.home() / "Downloads" / "FlowSnip")
    video_quality: str = Field(default=VIDEO_QUALITY_PRESETS["Best Quality"])
    audio_only: bool = Field(default=False)
    audio_quality: str = Field(default="best")
    retry_attempts: int = Field(default=2, ge=1, le=5)
    cookies_file: str | None = Field(default=None)
    cookies_from_browser: str | None = Field(default=None)

    @field_validator("video_quality")
    @classmethod
    def migrate_legacy_video_quality(cls, v: str) -> str:
        """Replace preset strings saved by older versions with their current form."""
        return _LEGACY_VIDEO_QUALITY.get(v, v)

    @field_validator("download_directory")
    @classmethod
    def validate_download_directory(cls, v: Path | str) -> Path:
        """Ensure download directory exists."""
        if isinstance(v, str):
            v = Path(v)  # pragma: no cover
        v.mkdir(parents=True, exist_ok=True)
        return v


class UIConfig(BaseModel):
    """Configuration for UI appearance and behavior."""

    theme: str = Field(default="dark")
    window_width: int = Field(default=1200, ge=800, le=2560)
    window_height: int = Field(default=800, ge=600, le=1440)
    auto_start_downloads: bool = Field(default=True)
    show_progress_details: bool = Field(default=True)
    minimize_to_tray: bool = Field(default=False)
    auto_remove_completed: bool = Field(default=False)


class YtdlConfig(BaseModel):
    """Configuration for yt-dlp specific options."""

    extract_flat: bool = Field(default=False)
    write_info_json: bool = Field(default=False)
    write_description: bool = Field(default=False)
    embed_subs: bool = Field(default=True)
    add_metadata: bool = Field(default=True)
    custom_args: list[str] = Field(default_factory=list)


class UpdateConfig(BaseModel):
    """Configuration for the auto-updater."""

    check_flowsnip: bool = Field(default=True)
    check_ytdlp: bool = Field(default=True)
    frequency: str = Field(default="daily")
    last_checked: datetime | None = Field(default=None)

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        allowed = {"every_launch", "daily", "weekly", "never"}
        if v not in allowed:
            raise ValueError(f"frequency must be one of {allowed}")
        return v


class Config(BaseSettings):
    """Main configuration class for FlowSnip."""

    download: DownloadConfig = Field(default_factory=DownloadConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    ytdl: YtdlConfig = Field(default_factory=YtdlConfig)
    updates: UpdateConfig = Field(default_factory=UpdateConfig)

    model_config = {
        "env_prefix": "FLOWSNIP_",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
    }

    def save_to_file(self, config_path: str | Path) -> None:
        """Save configuration to a JSON file."""
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path objects
        config_dict = self.model_dump(mode="json")
        self._convert_paths_to_strings(config_dict)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, config_path: str | Path) -> Config:
        """Load configuration from a JSON file."""
        config_path = Path(config_path)

        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        return cls(**config_data)

    def _convert_paths_to_strings(self, obj: dict | list | Any) -> None:
        """Recursively convert Path objects to strings for JSON serialization."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, Path):
                    obj[key] = str(value)
                elif isinstance(value, (dict, list)):
                    self._convert_paths_to_strings(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, Path):
                    obj[i] = str(item)
                elif isinstance(item, (dict, list)):
                    self._convert_paths_to_strings(item)

    def update_from_args(self, args: argparse.Namespace) -> None:
        """Update configuration from command line arguments."""
        if hasattr(args, "download_dir") and args.download_dir:
            self.download.download_directory = Path(args.download_dir)

        if hasattr(args, "quality") and args.quality:
            self.download.video_quality = args.quality

        if hasattr(args, "audio_only") and args.audio_only is not None:
            self.download.audio_only = args.audio_only

        if hasattr(args, "audio_quality") and args.audio_quality:
            self.download.audio_quality = args.audio_quality

        if hasattr(args, "max_parallel") and args.max_parallel:
            self.download.max_parallel_downloads = args.max_parallel

        if hasattr(args, "theme") and args.theme:
            self.ui.theme = args.theme


def get_default_config_path() -> Path:
    """Get the default configuration file path."""
    if hasattr(Path, "home"):
        config_dir = Path.home() / ".config" / "flowsnip"
    else:  # pragma: no cover
        config_dir = Path("~/.config/flowsnip").expanduser()  # pragma: no cover

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def create_arg_parser() -> argparse.ArgumentParser:
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="FlowSnip: A modern GUI wrapper for yt-dlp",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  flowsnip                                  # Start with default settings
  flowsnip --config my-config.json          # Use custom config file
  flowsnip --download-dir ~/Videos          # Override download directory
  flowsnip --quality "bestvideo[height<=720]+bestaudio/best"    # Set video quality
  flowsnip --audio-only --audio-quality 320 # Audio-only downloads
  flowsnip --max-parallel 5                 # Set max parallel downloads
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to configuration file (default: ~/.config/flowsnip/config.json)",
    )

    parser.add_argument(
        "--download-dir", "-d", type=Path, help="Download directory path"
    )

    parser.add_argument(
        "--quality",
        "-q",
        type=str,
        help="Video quality selector (e.g., 'bestvideo[height<=1080]+bestaudio/best')",
    )

    parser.add_argument(
        "--audio-only", "-a", action="store_true", help="Download audio only"
    )

    parser.add_argument(
        "--audio-quality", type=str, help="Audio quality (e.g., 'best', '320', '192')"
    )

    parser.add_argument(
        "--max-parallel", "-p", type=int, help="Maximum number of parallel downloads"
    )

    parser.add_argument(
        "--theme", "-t", choices=["light", "dark", "auto"], help="UI theme"
    )

    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in command-line mode (not implemented yet)",
    )

    return parser
