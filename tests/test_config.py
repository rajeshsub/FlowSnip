"""Tests for flowsnip/config.py - targets 100% line coverage."""

import argparse
from pathlib import Path

import pytest
from ytdlp_formats import (
    ADAPTIVE_4K,
    HLS_ONLY_1080,
    VP9_ONLY_4K,
    select,
    selected_ids,
)

from flowsnip.config import (
    VIDEO_QUALITY_PRESETS,
    Config,
    DownloadConfig,
    UIConfig,
    UpdateConfig,
    YtdlConfig,
    create_arg_parser,
    get_default_config_path,
    video_quality_display_name,
)

# Preset strings shipped before resolution-first presets. Users who saved one of
# these still have it in config.json.
_LEGACY_PRESETS = {
    "Best Quality": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
    "8K (4320p)": "bestvideo[height<=4320][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=4320]+bestaudio/best[ext=mp4]/best",
    "4K (2160p)": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[ext=mp4]/best",
    "1440p": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[ext=mp4][height<=720]/best[height<=720]",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[ext=mp4][height<=480]/best[height<=480]",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[ext=mp4][height<=360]/best[height<=360]",
    "240p": "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=240]+bestaudio/best[ext=mp4][height<=240]/best[height<=240]",
}

# ---------------------------------------------------------------------------
# DownloadConfig
# ---------------------------------------------------------------------------


def test_download_config_defaults():
    cfg = DownloadConfig()
    assert cfg.max_parallel_downloads == 3
    assert cfg.audio_only is False
    assert cfg.audio_quality == "best"
    assert cfg.retry_attempts == 2
    assert cfg.cookies_file is None
    assert cfg.cookies_from_browser is None


@pytest.mark.parametrize("preset", sorted(_LEGACY_PRESETS))
def test_legacy_preset_strings_migrate_on_load(preset):
    cfg = DownloadConfig(video_quality=_LEGACY_PRESETS[preset])
    assert cfg.video_quality == VIDEO_QUALITY_PRESETS[preset]


def test_legacy_preset_migrates_when_loaded_from_file(temp_dir):
    path = temp_dir / "config.json"
    path.write_text(
        '{"download": {"video_quality": "%s"}}' % _LEGACY_PRESETS["4K (2160p)"]
    )
    cfg = Config.load_from_file(path)
    assert cfg.download.video_quality == VIDEO_QUALITY_PRESETS["4K (2160p)"]


def test_custom_quality_string_is_kept_as_is():
    cfg = DownloadConfig(video_quality="best[height<=720]")
    assert cfg.video_quality == "best[height<=720]"


def test_video_quality_display_name_for_preset_and_custom():
    assert video_quality_display_name(VIDEO_QUALITY_PRESETS["1080p"]) == "1080p"
    assert video_quality_display_name("best[height<=720]") == "Custom"


# ---------------------------------------------------------------------------
# Video quality presets resolved by yt-dlp's real format selector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset, expected_height",
    [
        ("Best Quality", 2160),
        ("8K (4320p)", 2160),
        ("4K (2160p)", 2160),
        ("1440p", 1440),
        ("1080p", 1080),
        ("720p", 720),
        ("480p", 480),
        ("360p", 360),
        ("240p", 240),
    ],
)
def test_preset_picks_highest_stream_within_cap_when_top_tiers_are_vp9_only(
    preset, expected_height
):
    info = select(VIDEO_QUALITY_PRESETS[preset], VP9_ONLY_4K)
    assert info["height"] == expected_height
    assert len(selected_ids(info)) == 2  # separate video + audio, merged


def test_4k_preset_prefers_av1_over_vp9_at_same_height():
    info = select(VIDEO_QUALITY_PRESETS["4K (2160p)"], ADAPTIVE_4K)
    assert selected_ids(info) == ["401", "251"]


def test_best_quality_on_hls_only_list_falls_back_to_combined_1080p():
    # What a signed-in session returned with yt-dlp 2026.07.04: no video-only
    # streams, so /best takes the pre-merged 1080p stream.
    info = select(VIDEO_QUALITY_PRESETS["Best Quality"], HLS_ONLY_1080)
    assert selected_ids(info) == ["96"]
    assert info["height"] == 1080


def test_download_config_creates_directory(temp_dir):
    target = temp_dir / "new_subdir"
    cfg = DownloadConfig(download_directory=str(target))
    assert cfg.download_directory.is_dir()


def test_download_config_accepts_path_object(temp_dir):
    target = temp_dir / "subdir2"
    cfg = DownloadConfig(download_directory=target)
    assert cfg.download_directory == target


# ---------------------------------------------------------------------------
# UIConfig / YtdlConfig
# ---------------------------------------------------------------------------


def test_ui_config_defaults():
    cfg = UIConfig()
    assert cfg.theme == "dark"
    assert cfg.window_width == 1200
    assert cfg.window_height == 800
    assert cfg.auto_start_downloads is True
    assert cfg.show_progress_details is True
    assert cfg.minimize_to_tray is False
    assert cfg.auto_remove_completed is False


def test_ytdl_config_defaults():
    cfg = YtdlConfig()
    assert cfg.extract_flat is False
    assert cfg.write_info_json is False
    assert cfg.embed_subs is True
    assert cfg.add_metadata is True
    assert cfg.custom_args == []


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = Config()
    assert cfg.download.max_parallel_downloads == 3
    assert cfg.ui.theme == "dark"
    assert cfg.ytdl.add_metadata is True


def test_config_save_and_load(temp_dir):
    cfg = Config()
    cfg.download.max_parallel_downloads = 5
    cfg.ui.theme = "light"
    path = temp_dir / "cfg.json"
    cfg.save_to_file(path)
    assert path.exists()

    loaded = Config.load_from_file(path)
    assert loaded.download.max_parallel_downloads == 5
    assert loaded.ui.theme == "light"


def test_config_save_creates_parent_dirs(temp_dir):
    cfg = Config()
    deep = temp_dir / "a" / "b" / "cfg.json"
    cfg.save_to_file(deep)
    assert deep.exists()


def test_config_load_missing_file():
    cfg = Config.load_from_file(Path("/nonexistent/path/cfg.json"))
    assert cfg.download.max_parallel_downloads == 3  # defaults


def test_config_convert_paths_in_dict(temp_dir):
    cfg = Config()
    obj = {"dir": Path("/some/path"), "nested": {"dir2": Path("/other")}}
    cfg._convert_paths_to_strings(obj)
    assert obj["dir"] == str(Path("/some/path"))
    assert obj["nested"]["dir2"] == str(Path("/other"))


def test_config_convert_paths_in_list(temp_dir):
    cfg = Config()
    pa, pb, pc = Path("/a"), Path("/b"), Path("/c")
    obj = [pa, [pb, {"dir": pc}]]
    cfg._convert_paths_to_strings(obj)
    assert obj[0] == str(pa)
    assert obj[1][0] == str(pb)
    assert obj[1][1]["dir"] == str(pc)


# ---------------------------------------------------------------------------
# update_from_args
# ---------------------------------------------------------------------------


def _args(**kwargs):
    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def test_update_from_args_all_set(temp_dir):
    cfg = Config()
    args = _args(
        download_dir=temp_dir / "dl",
        quality="bestvideo+bestaudio/best",
        audio_only=True,
        audio_quality="320",
        max_parallel=4,
        theme="light",
    )
    cfg.update_from_args(args)
    assert cfg.download.download_directory == temp_dir / "dl"
    assert cfg.download.video_quality == "bestvideo+bestaudio/best"
    assert cfg.download.audio_only is True
    assert cfg.download.audio_quality == "320"
    assert cfg.download.max_parallel_downloads == 4
    assert cfg.ui.theme == "light"


def test_update_from_args_none_values():
    cfg = Config()
    # All falsy / None - nothing should change
    args = _args(
        download_dir=None,
        quality=None,
        audio_only=None,
        audio_quality=None,
        max_parallel=None,
        theme=None,
    )
    original_parallel = cfg.download.max_parallel_downloads
    cfg.update_from_args(args)
    assert cfg.download.max_parallel_downloads == original_parallel


def test_update_from_args_missing_attrs():
    cfg = Config()
    # Namespace with NO relevant attributes
    cfg.update_from_args(argparse.Namespace())


# ---------------------------------------------------------------------------
# get_default_config_path
# ---------------------------------------------------------------------------


def test_get_default_config_path():
    path = get_default_config_path()
    assert path.name == "config.json"
    assert path.parent.exists()


def test_default_config_path_is_isolated_from_real_home(real_home, _isolated_home):
    # GUI tests call on_closing(), which saves to this path; it must never be
    # the developer's real config.
    path = get_default_config_path()
    assert path == _isolated_home / ".config" / "flowsnip" / "config.json"
    assert path != real_home / ".config" / "flowsnip" / "config.json"


# ---------------------------------------------------------------------------
# create_arg_parser
# ---------------------------------------------------------------------------


def test_create_arg_parser_help():
    parser = create_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])


# ---------------------------------------------------------------------------
# UpdateConfig
# ---------------------------------------------------------------------------


def test_update_config_defaults():
    cfg = UpdateConfig()
    assert cfg.check_flowsnip is True
    assert cfg.check_ytdlp is True
    assert cfg.frequency == "daily"
    assert cfg.last_checked is None


def test_update_config_invalid_frequency():
    with pytest.raises(Exception):
        UpdateConfig(frequency="hourly")


def test_update_config_valid_frequencies():
    for freq in ("every_launch", "daily", "weekly", "never"):
        cfg = UpdateConfig(frequency=freq)
        assert cfg.frequency == freq


def test_update_config_roundtrip(temp_dir):
    from datetime import datetime, timezone

    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    cfg = Config()
    cfg.updates.check_flowsnip = False
    cfg.updates.check_ytdlp = False
    cfg.updates.frequency = "weekly"
    cfg.updates.last_checked = now
    path = temp_dir / "cfg.json"
    cfg.save_to_file(path)

    loaded = Config.load_from_file(path)
    assert loaded.updates.check_flowsnip is False
    assert loaded.updates.check_ytdlp is False
    assert loaded.updates.frequency == "weekly"
    assert loaded.updates.last_checked is not None


def test_config_defaults_include_updates():
    cfg = Config()
    assert cfg.updates.check_flowsnip is True
    assert cfg.updates.frequency == "daily"


def test_create_arg_parser_all_flags(temp_dir):
    parser = create_arg_parser()
    args = parser.parse_args(
        [
            "--download-dir",
            str(temp_dir),
            "--quality",
            "bestvideo+bestaudio/best",
            "--audio-only",
            "--audio-quality",
            "320",
            "--max-parallel",
            "3",
            "--theme",
            "light",
            "--no-gui",
        ]
    )
    assert args.theme == "light"
    assert args.audio_only is True
    assert args.max_parallel == 3


# ---------------------------------------------------------------------------
# _convert_paths_to_strings - branch coverage
# ---------------------------------------------------------------------------


def test_config_convert_paths_non_container():
    cfg = Config()
    cfg._convert_paths_to_strings(42)  # neither dict nor list - no-op


def test_config_convert_paths_list_with_scalar_item():
    cfg = Config()
    obj = ["plain_string", 42, None]
    cfg._convert_paths_to_strings(obj)
    assert obj == ["plain_string", 42, None]
