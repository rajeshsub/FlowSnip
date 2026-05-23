"""Tests for flowsnip/config.py — targets 100% line coverage."""

import argparse
from pathlib import Path

import pytest

from flowsnip.config import (
    Config,
    DownloadConfig,
    UIConfig,
    YtdlConfig,
    create_arg_parser,
    get_default_config_path,
)

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


def test_ytdl_config_defaults():
    cfg = YtdlConfig()
    assert cfg.extract_flat is False
    assert cfg.write_info_json is False
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
    # All falsy / None — nothing should change
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


# ---------------------------------------------------------------------------
# create_arg_parser
# ---------------------------------------------------------------------------


def test_create_arg_parser_help():
    parser = create_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])


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
