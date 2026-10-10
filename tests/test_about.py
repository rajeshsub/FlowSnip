"""Tests for flowsnip/about.py."""

import tkinter as tk
from unittest.mock import MagicMock, patch

import customtkinter as ctk
from yt_dlp.version import __version__ as YTDLP_VERSION

from flowsnip.about import PROJECT_URL, AboutDialog


def _build(version="1.2.3"):
    """Build the dialog with label/button widgets recorded."""
    with (
        patch("flowsnip.about.__version__", version),
        patch.object(ctk, "CTkLabel") as label,
        patch.object(ctk, "CTkButton") as button,
    ):
        AboutDialog(MagicMock())
    texts = [c.kwargs.get("text", "") for c in label.call_args_list]
    return texts, button.call_args_list


def test_about_dialog_shows_flowsnip_and_ytdlp_versions():
    texts, _ = _build("1.2.3")
    assert "Version 1.2.3" in texts
    assert f"yt-dlp {YTDLP_VERSION}" in texts


def test_about_dialog_shows_project_url():
    texts, _ = _build()
    assert PROJECT_URL in texts


def test_about_dialog_hides_unknown_version():
    texts, _ = _build("unknown")
    assert not any(t.lower().startswith("version") for t in texts)
    assert not any("unknown" in t.lower() for t in texts)


def test_about_github_button_opens_the_project_page():
    _, buttons = _build()
    github = next(c for c in buttons if c.kwargs.get("text") == "GitHub")
    with patch("flowsnip.about.webbrowser.open") as opened:
        github.kwargs["command"]()
    opened.assert_called_once_with(PROJECT_URL)


def test_about_close_button_closes_the_dialog():
    with (
        patch("flowsnip.about.__version__", "1.2.3"),
        patch.object(ctk, "CTkLabel"),
        patch.object(ctk, "CTkButton") as button,
        patch.object(AboutDialog, "destroy") as destroy,
    ):
        AboutDialog(MagicMock())
    close = next(c for c in button.call_args_list if c.kwargs.get("text") == "Close")
    close.kwargs["command"]()
    destroy.assert_called_once()


def test_about_escape_closes_the_dialog():
    with (
        patch("flowsnip.about.__version__", "1.2.3"),
        patch.object(ctk, "CTkLabel"),
        patch.object(ctk, "CTkButton"),
        patch.object(AboutDialog, "bind") as bind,
        patch.object(AboutDialog, "destroy") as destroy,
    ):
        AboutDialog(MagicMock())
        sequence, handler = bind.call_args.args
        assert sequence == "<Escape>"
        handler(None)
        destroy.assert_called_once()


def _dialog_with_grab_mocks():
    dialog = object.__new__(AboutDialog)
    dialog.winfo_exists = MagicMock(return_value=True)
    dialog.grab_set = MagicMock()
    dialog.focus_force = MagicMock()
    return dialog


def test_take_focus_grabs_and_focuses_a_visible_dialog():
    dialog = _dialog_with_grab_mocks()
    dialog._take_focus()
    dialog.grab_set.assert_called_once()
    dialog.focus_force.assert_called_once()


def test_take_focus_skips_a_dialog_closed_before_the_delay():
    dialog = _dialog_with_grab_mocks()
    dialog.winfo_exists.return_value = False
    dialog._take_focus()
    dialog.grab_set.assert_not_called()


def test_take_focus_tolerates_a_window_that_is_not_viewable_yet():
    dialog = _dialog_with_grab_mocks()
    dialog.grab_set.side_effect = tk.TclError("grab failed: window not viewable")
    dialog._take_focus()  # must not raise
