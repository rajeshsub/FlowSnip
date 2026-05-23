"""Tests for flowsnip/main.py — targets 100% line coverage."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from flowsnip.main import main

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


# ---------------------------------------------------------------------------
# main() — normal GUI path
# ---------------------------------------------------------------------------


def test_main_gui_path():
    mock_args = _default_args()
    mock_app = MagicMock()

    with (
        patch("flowsnip.main.create_arg_parser") as mock_parser_factory,
        patch("flowsnip.main.get_default_config_path", return_value=Path("cfg.json")),
        patch("flowsnip.main.Config.load_from_file") as mock_load,
        patch("flowsnip.main.FlowSnipGUI", return_value=mock_app),
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


def test_main_uses_args_config():
    """When args.config is set it is used instead of default path."""
    mock_args = _default_args(config="/custom/cfg.json")
    mock_app = MagicMock()

    with (
        patch("flowsnip.main.create_arg_parser") as mock_factory,
        patch("flowsnip.main.get_default_config_path") as mock_default,
        patch("flowsnip.main.Config.load_from_file") as mock_load,
        patch("flowsnip.main.FlowSnipGUI", return_value=mock_app),
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
