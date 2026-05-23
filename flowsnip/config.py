"""
Configuration management for FlowSnip.

Handles loading, saving, and validation of application settings using Pydantic.
Supports both file-based configuration and command-line overrides.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class DownloadConfig(BaseModel):
    """Configuration for download behavior."""

    max_parallel_downloads: int = Field(default=3, ge=1, le=10)
    download_directory: Path = Field(default=Path.home() / "Downloads" / "FlowSnip")
    video_quality: str = Field(
        default="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
    )
    audio_only: bool = Field(default=False)
    audio_quality: str = Field(default="best")
    retry_attempts: int = Field(default=2, ge=1, le=5)
    cookies_file: Optional[str] = Field(default=None)
    cookies_from_browser: Optional[str] = Field(default=None)

    @field_validator("download_directory")
    @classmethod
    def validate_download_directory(cls, v):
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


class YtdlConfig(BaseModel):
    """Configuration for yt-dlp specific options."""

    extract_flat: bool = Field(default=False)
    write_info_json: bool = Field(default=False)
    write_description: bool = Field(default=False)
    write_thumbnail: bool = Field(default=False)
    embed_subs: bool = Field(default=False)
    embed_thumbnail: bool = Field(default=False)
    add_metadata: bool = Field(default=True)
    custom_args: List[str] = Field(default_factory=list)


class Config(BaseSettings):
    """Main configuration class for FlowSnip."""

    download: DownloadConfig = Field(default_factory=DownloadConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    ytdl: YtdlConfig = Field(default_factory=YtdlConfig)

    model_config = {
        "env_prefix": "FLOWSNIP_",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
    }

    def save_to_file(self, config_path: Union[str, Path]) -> None:
        """Save configuration to a JSON file."""
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle Path objects
        config_dict = self.model_dump()
        self._convert_paths_to_strings(config_dict)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, config_path: Union[str, Path]) -> "Config":
        """Load configuration from a JSON file."""
        config_path = Path(config_path)

        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        return cls(**config_data)

    def _convert_paths_to_strings(self, obj: Union[Dict, List, Any]) -> None:
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
