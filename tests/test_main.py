"""Tests for flowsnip/main.py — targets 100% line coverage."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from flowsnip.main import _apply_ytdlp_update, _run_update_checks, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_args(**overrides):
    args = argparse.Namespace(
        config=None,
        download_dir=None,
        quality=None,
        audio_only=None,
        audio_quality=None,
        max_parallel=None,
        theme=None,
        no_gui=False,
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_app():
    app = MagicMock()
    app.root = MagicMock()
    app._dismiss_update_banner = MagicMock()
    return app


# ---------------------------------------------------------------------------
# main() — normal GUI path
# ---------------------------------------------------------------------------


def test_main_gui_path():
    mock_args = _default_args()
    mock_app = _make_app()

    with (
        patch("flowsnip.main.create_arg_parser") as mock_parser_factory,
        patch("flowsnip.main.get_default_config_path", return_value=Path("cfg.json")),
        patch("flowsnip.main.Config.load_from_file") as mock_load,
        patch("flowsnip.main.FlowSnipGUI", return_value=mock_app),
        patch("flowsnip.main.threading.Thread"),
    ):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_parser_factory.return_value = mock_parser

        mock_config = MagicMock()
        mock_load.return_value = mock_config

        result = main()

    assert result == 0
    mock_app.run.assert_called_once()
    mock_config.update_from_args.assert_called_once_with(mock_args)


def test_main_gui_path_updates_disabled():
    """When both update checks are off, no Thread is started."""
    mock_args = _default_args()
    mock_app = _make_app()

    with (
        patch("flowsnip.main.create_arg_parser") as mock_parser_factory,
        patch("flowsnip.main.get_default_config_path", return_value=Path("cfg.json")),
        patch("flowsnip.main.Config.load_from_file") as mock_load,
        patch("flowsnip.main.FlowSnipGUI", return_value=mock_app),
        patch("flowsnip.main.threading.Thread") as MockThread,
    ):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_parser_factory.return_value = mock_parser

        from flowsnip.config import Config

        cfg = Config()
        cfg.updates.check_flowsnip = False
        cfg.updates.check_ytdlp = False
        mock_load.return_value = cfg

        result = main()

    assert result == 0
    MockThread.assert_not_called()


def test_main_uses_args_config():
    """When args.config is set it is used instead of default path."""
    mock_args = _default_args(config="/custom/cfg.json")
    mock_app = _make_app()

    with (
        patch("flowsnip.main.create_arg_parser") as mock_factory,
        patch("flowsnip.main.get_default_config_path") as mock_default,
        patch("flowsnip.main.Config.load_from_file") as mock_load,
        patch("flowsnip.main.FlowSnipGUI", return_value=mock_app),
        patch("flowsnip.main.threading.Thread"),
    ):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_factory.return_value = mock_parser
        mock_load.return_value = MagicMock()

        main()

    mock_default.assert_not_called()
    mock_load.assert_called_once_with("/custom/cfg.json")


# ---------------------------------------------------------------------------
# main() — no_gui path
# ---------------------------------------------------------------------------


def test_main_no_gui():
    mock_args = _default_args(no_gui=True)

    with (
        patch("flowsnip.main.create_arg_parser") as mock_factory,
        patch("flowsnip.main.get_default_config_path", return_value=Path("cfg.json")),
        patch("flowsnip.main.Config.load_from_file", return_value=MagicMock()),
        patch("flowsnip.main.FlowSnipGUI") as mock_gui,
    ):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_factory.return_value = mock_parser

        result = main()

    assert result == 1
    mock_gui.assert_not_called()


# ---------------------------------------------------------------------------
# main() — exception paths
# ---------------------------------------------------------------------------


def test_main_keyboard_interrupt():
    with patch("flowsnip.main.create_arg_parser") as mock_factory:
        mock_parser = MagicMock()
        mock_parser.parse_args.side_effect = KeyboardInterrupt()
        mock_factory.return_value = mock_parser

        result = main()

    assert result == 1


def test_main_generic_exception():
    with patch("flowsnip.main.create_arg_parser") as mock_factory:
        mock_parser = MagicMock()
        mock_parser.parse_args.side_effect = RuntimeError("unexpected error")
        mock_factory.return_value = mock_parser

        result = main()

    assert result == 1


# ---------------------------------------------------------------------------
# _run_update_checks
# ---------------------------------------------------------------------------


def test_run_update_checks_should_not_check():
    """Early return when should_check is False."""
    app = _make_app()
    config = MagicMock()
    with patch("flowsnip.main.updater.should_check", return_value=False):
        _run_update_checks(app, config, Path("/cfg.json"))
    app.root.after.assert_not_called()


def test_run_update_checks_flowsnip_new_version(temp_dir):
    from flowsnip.config import Config

    app = _make_app()
    config = Config()
    config.updates.check_flowsnip = True
    config.updates.check_ytdlp = False
    config_path = temp_dir / "cfg.json"

    with (
        patch("flowsnip.main.updater.should_check", return_value=True),
        patch("flowsnip.main.updater.check_flowsnip_update", return_value="v9.9.9"),
        patch("flowsnip.main.webbrowser.open") as mock_open,
    ):
        _run_update_checks(app, config, config_path)
        assert config.updates.last_checked is not None
        after_cb = app.root.after.call_args[0][1]
        after_cb()
        show_args = app.show_update_banner.call_args[0]
        assert "v9.9.9" in show_args[0]
        action_cb = show_args[2]
        action_cb()
        mock_open.assert_called_once()


def test_run_update_checks_flowsnip_no_new_version(temp_dir):
    from flowsnip.config import Config

    app = _make_app()
    config = Config()
    config.updates.check_flowsnip = True
    config.updates.check_ytdlp = False
    config_path = temp_dir / "cfg.json"

    with (
        patch("flowsnip.main.updater.should_check", return_value=True),
        patch("flowsnip.main.updater.check_flowsnip_update", return_value=None),
    ):
        _run_update_checks(app, config, config_path)

    app.root.after.assert_not_called()


def test_run_update_checks_flowsnip_disabled(temp_dir):
    from flowsnip.config import Config

    app = _make_app()
    config = Config()
    config.updates.check_flowsnip = False
    config.updates.check_ytdlp = False
    config_path = temp_dir / "cfg.json"

    with patch("flowsnip.main.updater.should_check", return_value=True):
        _run_update_checks(app, config, config_path)

    app.root.after.assert_not_called()


def test_run_update_checks_ytdlp_new_version(temp_dir):
    from flowsnip.config import Config

    app = _make_app()
    config = Config()
    config.updates.check_flowsnip = False
    config.updates.check_ytdlp = True
    config_path = temp_dir / "cfg.json"

    with (
        patch("flowsnip.main.updater.should_check", return_value=True),
        patch("flowsnip.main.updater.check_ytdlp_update", return_value="2026.12.01"),
        patch("flowsnip.main.threading.Thread") as MockThread,
    ):
        _run_update_checks(app, config, config_path)
        assert config.updates.last_checked is not None
        after_cb = app.root.after.call_args[0][1]
        after_cb()
        show_args = app.show_update_banner.call_args[0]
        assert "2026.12.01" in show_args[0]
        action_cb = show_args[2]
        action_cb()
        MockThread.assert_called_once()
        MockThread.return_value.start.assert_called_once()


def test_run_update_checks_ytdlp_no_new_version(temp_dir):
    from flowsnip.config import Config

    app = _make_app()
    config = Config()
    config.updates.check_flowsnip = False
    config.updates.check_ytdlp = True
    config_path = temp_dir / "cfg.json"

    with (
        patch("flowsnip.main.updater.should_check", return_value=True),
        patch("flowsnip.main.updater.check_ytdlp_update", return_value=None),
    ):
        _run_update_checks(app, config, config_path)

    app.root.after.assert_not_called()


# ---------------------------------------------------------------------------
# _apply_ytdlp_update
# ---------------------------------------------------------------------------


def test_apply_ytdlp_update_success():
    app = _make_app()
    with patch("flowsnip.main.updater.update_ytdlp", return_value=True):
        _apply_ytdlp_update(app, "2026.12.01")
    after_cb = app.root.after.call_args[0][1]
    after_cb()
    msg = app.show_update_banner.call_args[0][0]
    assert "updated" in msg


def test_apply_ytdlp_update_failure():
    app = _make_app()
    with patch("flowsnip.main.updater.update_ytdlp", return_value=False):
        _apply_ytdlp_update(app, "2026.12.01")
    after_cb = app.root.after.call_args[0][1]
    after_cb()
    msg = app.show_update_banner.call_args[0][0]
    assert "failed" in msg
