"""Tests for flowsnip/gui.py — targets 100% line coverage."""

# conftest.py has already injected customtkinter/tkinter stubs into sys.modules.
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Access the stubs that conftest.py injected so helpers can use StringVar/BooleanVar
_CTK_STUB = sys.modules["customtkinter"]

from flowsnip.config import Config  # noqa: E402
from flowsnip.download_manager import DownloadItem, DownloadStatus  # noqa: E402
from flowsnip.gui import ConfigFrame, FlowSnipGUI, ProgressFrame  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (avoid repeating magic strings and numbers throughout tests)
# ---------------------------------------------------------------------------

_QUALITY_BEST = (
    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
)
_QUALITY_1080P = (
    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
    "/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best"
)
_LOG_LINE_LIMIT = 1000
_AUTO_REMOVE_DELAY_MS = 1500
_THROTTLE_THRESHOLD_S = 0.1
_STATS_POLL_ACTIVE_MS = 1000
_STATS_POLL_IDLE_MS = 5000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    status=DownloadStatus.PENDING,
    progress=0.0,
    speed=None,
    title="Test Video",
):
    item = DownloadItem(url="https://example.com/v=1", title=title)
    item.status = status
    item.progress = progress
    item.speed = speed
    return item


_SENTINEL = object()


def _make_progress_frame(item=None, manager=_SENTINEL):
    """Instantiate ProgressFrame without calling __init__ (skips widget creation)."""
    pf = object.__new__(ProgressFrame)
    pf.download_item = item or _make_item()
    pf.download_manager = MagicMock() if manager is _SENTINEL else manager
    pf.progress_bar = MagicMock()
    pf.status_label = MagicMock()
    pf.speed_label = MagicMock()
    pf.cancel_button = MagicMock()
    return pf


def _make_config_frame(config=None):
    """Instantiate ConfigFrame without calling __init__."""
    cf = object.__new__(ConfigFrame)
    cf.config_obj = config or Config()
    cf.browser_var = _CTK_STUB.StringVar(value="Not set")
    cf.audio_only_var = _CTK_STUB.BooleanVar(value=False)
    cf.audio_quality_var = _CTK_STUB.StringVar(value="best")
    cf.audio_quality_row = 10
    cf.audio_quality_label = MagicMock()
    cf.audio_quality_combobox = MagicMock()
    cf.quality_var = _CTK_STUB.StringVar(value="Best Quality")
    cf.quality_combobox = MagicMock()
    cf.download_dir_label = MagicMock()
    cf.parallel_slider = MagicMock()
    cf.parallel_value_label = MagicMock()
    cf.auto_start_var = _CTK_STUB.BooleanVar(value=True)
    cf.auto_remove_completed_var = _CTK_STUB.BooleanVar(value=False)
    cf.embed_subs_var = _CTK_STUB.BooleanVar(value=True)
    cf.quality_options = {
        "Best Quality": _QUALITY_BEST,
        "1080p": _QUALITY_1080P,
    }
    cf.quality_var = _CTK_STUB.StringVar(value="Best Quality")
    cf.theme_var = _CTK_STUB.StringVar(value="dark")
    cf.theme_combobox = MagicMock()
    cf.check_flowsnip_var = _CTK_STUB.BooleanVar(value=True)
    cf.check_ytdlp_var = _CTK_STUB.BooleanVar(value=True)
    cf.update_frequency_var = _CTK_STUB.StringVar(value="daily")
    cf.last_checked_label = MagicMock()
    return cf


def _make_gui(config=None):
    """Instantiate FlowSnipGUI without calling __init__."""
    g = object.__new__(FlowSnipGUI)
    g.config = config or Config()
    g.download_manager = MagicMock()
    g.download_manager.is_running = False
    g.download_manager.is_paused = False
    g.progress_frames = {}
    g.root = MagicMock()
    g.root.geometry.return_value = "1200x800+0+0"
    g.url_textbox = MagicMock()
    g.url_textbox.get.return_value = ""
    g.start_button = MagicMock()
    g.pause_button = MagicMock()
    g.stop_button = MagicMock()
    g.open_folder_button = MagicMock()
    g.status_label = MagicMock()
    g.status_label.winfo_exists.return_value = True
    g.downloads_scroll = MagicMock()
    g.log_textbox = MagicMock()
    g.log_textbox.get.return_value = ""
    g.stats_labels = {
        "active": MagicMock(),
        "completed": MagicMock(),
        "failed": MagicMock(),
        "total": MagicMock(),
    }
    g.config_frame = MagicMock()
    g.stats_frame = MagicMock()
    g._last_ui_update = {}
    g._log_line_count = 0
    g._update_banner = MagicMock()
    g._update_banner_label = MagicMock()
    g._update_banner_action = MagicMock()
    return g


# ---------------------------------------------------------------------------
# ProgressFrame.setup_ui (via __init__)
# ---------------------------------------------------------------------------


def test_progress_frame_init_short_title():
    dm = MagicMock()
    item = _make_item(title="Short Title")
    pf = ProgressFrame.__new__(ProgressFrame)
    pf.download_item = item
    pf.download_manager = dm
    pf.setup_ui()
    assert pf.download_item is item


def test_progress_frame_init_long_title():
    dm = MagicMock()
    item = _make_item(title="A" * 70)
    pf = ProgressFrame.__new__(ProgressFrame)
    pf.download_item = item
    pf.download_manager = dm
    pf.setup_ui()


# ---------------------------------------------------------------------------
# ProgressFrame.update_progress
# ---------------------------------------------------------------------------


def test_update_progress_downloading_with_progress():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.DOWNLOADING, progress=50.0, speed="1 Mbps")
    pf.update_progress(item)
    pf.status_label.configure.assert_called()
    pf.speed_label.configure.assert_called()


def test_update_progress_downloading_zero_progress():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.DOWNLOADING, progress=0.0)
    pf.update_progress(item)
    call_args = pf.status_label.configure.call_args
    assert "Initializing" in call_args[1]["text"]


def test_update_progress_non_downloading_with_progress():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.PAUSED, progress=30.0)
    pf.update_progress(item)
    call_args = pf.status_label.configure.call_args
    assert "30.0" in call_args[1]["text"]


def test_update_progress_completed_no_progress_suffix():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.COMPLETED, progress=100.0)
    pf.update_progress(item)
    pf.cancel_button.configure.assert_called()
    call_kw = pf.cancel_button.configure.call_args[1]
    assert call_kw["text"] == "Remove"


def test_update_progress_cancelled_button_remove():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.CANCELLED, progress=0.0)
    pf.update_progress(item)
    call_kw = pf.cancel_button.configure.call_args[1]
    assert call_kw["text"] == "Remove"


def test_update_progress_failed_button_retry():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.FAILED, progress=0.0)
    pf.update_progress(item)
    call_kw = pf.cancel_button.configure.call_args[1]
    assert call_kw["text"] == "Retry"


def test_update_progress_non_downloading_zero_progress_no_suffix():
    pf = _make_progress_frame()
    item = _make_item(status=DownloadStatus.PENDING, progress=0.0)
    pf.update_progress(item)
    call_args = pf.status_label.configure.call_args
    assert "%" not in call_args[1]["text"]


# ---------------------------------------------------------------------------
# ProgressFrame action methods
# ---------------------------------------------------------------------------


def test_cancel_download_calls_manager():
    dm = MagicMock()
    item = _make_item()
    pf = _make_progress_frame(item=item, manager=dm)
    pf.cancel_download()
    dm.cancel_download.assert_called_once_with(item.id)


def test_cancel_download_no_manager():
    pf = _make_progress_frame(manager=None)
    pf.cancel_download()


def test_remove_download_completed():
    dm = MagicMock()
    item = _make_item(status=DownloadStatus.COMPLETED)
    pf = _make_progress_frame(item=item, manager=dm)
    pf.remove_download()
    dm.remove_download.assert_called_once_with(item.id, "completed")


def test_remove_download_failed():
    dm = MagicMock()
    item = _make_item(status=DownloadStatus.FAILED)
    pf = _make_progress_frame(item=item, manager=dm)
    pf.remove_download()
    dm.remove_download.assert_called_once_with(item.id, "failed")


def test_remove_download_no_manager():
    pf = _make_progress_frame(manager=None)
    pf.remove_download()


def test_retry_download_calls_manager():
    dm = MagicMock()
    item = _make_item()
    pf = _make_progress_frame(item=item, manager=dm)
    pf.retry_download()
    dm.retry_download.assert_called_once_with(item.id)


def test_retry_download_no_manager():
    pf = _make_progress_frame(manager=None)
    pf.retry_download()


# ---------------------------------------------------------------------------
# ConfigFrame.__init__
# ---------------------------------------------------------------------------


def test_config_frame_init(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    parent = MagicMock()
    cf = ConfigFrame(parent, config)
    assert cf.config_obj is config


# ---------------------------------------------------------------------------
# FlowSnipGUI.__init__ / setup_window / setup_ui / setup_stats_tab
# ---------------------------------------------------------------------------


def test_finish_ui_setup(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    g = _make_gui(config=config)
    g.download_manager.get_queue_status.return_value = {
        "active_count": 0,
        "pending_count": 0,
        "completed_count": 0,
        "failed_count": 0,
    }
    g._finish_ui_setup()
    g.start_button.configure.assert_called()  # update_button_states ran


# ---------------------------------------------------------------------------
# FlowSnipGUI._show_disclaimer_modal
# ---------------------------------------------------------------------------


def test_show_disclaimer_modal_accept():
    g = _make_gui()
    with (
        patch("flowsnip.gui.messagebox.askyesno", return_value=True),
        patch("flowsnip.gui.sys.exit") as mock_exit,
    ):
        g._show_disclaimer_modal()
    mock_exit.assert_not_called()


def test_show_disclaimer_modal_decline():
    g = _make_gui()
    with (
        patch("flowsnip.gui.messagebox.askyesno", return_value=False),
        patch("flowsnip.gui.messagebox.showinfo"),
        patch("flowsnip.gui.sys.exit") as mock_exit,
    ):
        g._show_disclaimer_modal()
    mock_exit.assert_called_once_with(0)


def test_flowsnipgui_init(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    config.ui.auto_start_downloads = True
    with patch("flowsnip.gui.DownloadManager") as MockDM:
        mock_dm = MagicMock()
        mock_dm.is_running = False
        mock_dm.is_paused = False
        mock_dm.get_queue_status.return_value = {
            "active_count": 0,
            "pending_count": 0,
            "completed_count": 0,
            "failed_count": 0,
        }
        MockDM.return_value = mock_dm
        g = FlowSnipGUI(config)
    mock_dm.start_downloads.assert_called_once()
    assert g.config is config


# ---------------------------------------------------------------------------
# ConfigFrame.setup_ui (via instantiation — tests quality match logic)
# ---------------------------------------------------------------------------


def test_config_frame_setup_ui_quality_match(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    config.download.video_quality = _QUALITY_1080P
    cf = ConfigFrame.__new__(ConfigFrame)
    cf.config_obj = config
    cf.setup_ui()


def test_config_frame_setup_ui_quality_no_match(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    config.download.video_quality = "unknown/format"
    cf = ConfigFrame.__new__(ConfigFrame)
    cf.config_obj = config
    cf.setup_ui()


def test_config_frame_audio_only_shows_quality(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    config.download.audio_only = True
    cf = ConfigFrame.__new__(ConfigFrame)
    cf.config_obj = config
    cf.setup_ui()


# ---------------------------------------------------------------------------
# ConfigFrame methods
# ---------------------------------------------------------------------------


def test_on_audio_only_toggle_enable():
    cf = _make_config_frame()
    cf.audio_only_var.set(True)
    cf.on_audio_only_toggle()
    cf.quality_combobox.configure.assert_called_with(state="disabled")


def test_on_audio_only_toggle_disable():
    cf = _make_config_frame()
    cf.audio_only_var.set(False)
    cf.on_audio_only_toggle()
    cf.quality_combobox.configure.assert_called_with(state="normal")


def test_toggle_audio_quality_visibility_show():
    cf = _make_config_frame()
    cf.audio_only_var.set(True)
    cf.toggle_audio_quality_visibility()
    cf.audio_quality_label.grid.assert_called()
    cf.audio_quality_combobox.grid.assert_called()


def test_toggle_audio_quality_visibility_hide():
    cf = _make_config_frame()
    cf.audio_only_var.set(False)
    cf.toggle_audio_quality_visibility()
    cf.audio_quality_label.grid_remove.assert_called()
    cf.audio_quality_combobox.grid_remove.assert_called()


def test_browse_directory_selected():
    cf = _make_config_frame()
    with patch("flowsnip.gui.filedialog.askdirectory", return_value="/some/dir"):
        cf.browse_directory()
    assert cf.config_obj.download.download_directory == Path("/some/dir")
    cf.download_dir_label.configure.assert_called()


def test_browse_directory_cancelled():
    cf = _make_config_frame()
    original = cf.config_obj.download.download_directory
    with patch("flowsnip.gui.filedialog.askdirectory", return_value=""):
        cf.browse_directory()
    assert cf.config_obj.download.download_directory == original


def test_update_parallel_downloads():
    cf = _make_config_frame()
    cf.update_parallel_downloads(5.0)
    assert cf.config_obj.download.max_parallel_downloads == 5
    cf.parallel_value_label.configure.assert_called_with(text="5")


def test_update_video_quality_known():
    cf = _make_config_frame()
    cf.update_video_quality("1080p")
    assert "1080" in cf.config_obj.download.video_quality


def test_update_video_quality_unknown():
    cf = _make_config_frame()
    cf.update_video_quality("UnknownQuality")
    assert cf.config_obj.download.video_quality == "bestvideo+bestaudio/best"


def test_update_audio_only_true():
    cf = _make_config_frame()
    cf.audio_only_var.set(True)
    cf.update_audio_only()
    assert cf.config_obj.download.audio_only is True


def test_update_audio_only_false():
    cf = _make_config_frame()
    cf.audio_only_var.set(False)
    cf.update_audio_only()
    assert cf.config_obj.download.audio_only is False


def test_update_audio_quality():
    cf = _make_config_frame()
    cf.update_audio_quality("320")
    assert cf.config_obj.download.audio_quality == "320"


def test_update_embed_subs_true():
    cf = _make_config_frame()
    cf.embed_subs_var.set(True)
    cf.update_embed_subs()
    assert cf.config_obj.ytdl.embed_subs is True


def test_update_embed_subs_false():
    cf = _make_config_frame()
    cf.embed_subs_var.set(False)
    cf.update_embed_subs()
    assert cf.config_obj.ytdl.embed_subs is False


def test_update_theme():
    cf = _make_config_frame()
    with patch("flowsnip.gui.ctk.set_appearance_mode"):
        cf.update_theme("light")
    assert cf.config_obj.ui.theme == "light"


def test_update_auto_start():
    cf = _make_config_frame()
    cf.auto_start_var.set(False)
    cf.update_auto_start()
    assert cf.config_obj.ui.auto_start_downloads is False


def test_save_config_success(temp_dir):
    cf = _make_config_frame()
    save_path = str(temp_dir / "saved.json")
    with (
        patch("flowsnip.gui.filedialog.asksaveasfilename", return_value=save_path),
        patch("flowsnip.gui.messagebox.showinfo") as mock_info,
    ):
        cf.save_config()
    mock_info.assert_called_once()


def test_save_config_cancelled():
    cf = _make_config_frame()
    with (
        patch("flowsnip.gui.filedialog.asksaveasfilename", return_value=""),
        patch("flowsnip.gui.messagebox.showinfo") as mock_info,
    ):
        cf.save_config()
    mock_info.assert_not_called()


def test_save_config_error(temp_dir):
    cf = _make_config_frame()
    with (
        patch(
            "flowsnip.gui.filedialog.asksaveasfilename",
            return_value=str(temp_dir / "out.json"),
        ),
        patch("flowsnip.config.Config.save_to_file", side_effect=OSError("boom")),
        patch("flowsnip.gui.messagebox.showerror") as mock_err,
    ):
        cf.save_config()
    mock_err.assert_called_once()


def test_load_config_success(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    save_path = temp_dir / "cfg.json"
    config.save_to_file(save_path)

    cf = _make_config_frame()
    with (
        patch("flowsnip.gui.filedialog.askopenfilename", return_value=str(save_path)),
        patch("flowsnip.gui.messagebox.showinfo") as mock_info,
        patch.object(cf, "update_ui_from_config"),
    ):
        cf.load_config()
    mock_info.assert_called_once()


def test_load_config_cancelled():
    cf = _make_config_frame()
    with (
        patch("flowsnip.gui.filedialog.askopenfilename", return_value=""),
        patch("flowsnip.gui.messagebox.showinfo") as mock_info,
    ):
        cf.load_config()
    mock_info.assert_not_called()


def test_load_config_error():
    cf = _make_config_frame()
    with (
        patch("flowsnip.gui.filedialog.askopenfilename", return_value="/bad.json"),
        patch("flowsnip.gui.Config.load_from_file", side_effect=OSError("fail")),
        patch("flowsnip.gui.messagebox.showerror") as mock_err,
    ):
        cf.load_config()
    mock_err.assert_called_once()


def test_update_browser_cookies_not_set():
    cf = _make_config_frame()
    cf.update_browser_cookies("Not set")
    assert cf.config_obj.download.cookies_from_browser is None


def test_update_browser_cookies_value():
    cf = _make_config_frame()
    cf.update_browser_cookies("chrome")
    assert cf.config_obj.download.cookies_from_browser == "chrome"


def test_update_ui_from_config_quality_match():
    cf = _make_config_frame()
    cf.config_obj.download.video_quality = cf.quality_options["1080p"]
    cf.config_obj.download.audio_only = False
    cf.update_ui_from_config()
    assert cf.quality_var.get() == "1080p"


def test_update_ui_from_config_quality_no_match():
    cf = _make_config_frame()
    cf.config_obj.download.video_quality = "unknown_format"
    cf.update_ui_from_config()
    assert cf.quality_var.get() == "Best Quality"


def test_update_ui_from_config_browser_none():
    cf = _make_config_frame()
    cf.config_obj.download.cookies_from_browser = None
    cf.update_ui_from_config()
    assert cf.browser_var.get() == "Not set"


def test_update_ui_from_config_browser_set():
    cf = _make_config_frame()
    cf.config_obj.download.cookies_from_browser = "firefox"
    cf.update_ui_from_config()
    assert cf.browser_var.get() == "firefox"


# ---------------------------------------------------------------------------
# FlowSnipGUI.show_section
# ---------------------------------------------------------------------------


def test_show_section_downloads():
    g = _make_gui()
    g.show_section("Downloads")
    g.downloads_scroll.grid.assert_called()


def test_show_section_configuration():
    g = _make_gui()
    g.show_section("Configuration")
    g.config_frame.grid.assert_called()


def test_show_section_statistics():
    g = _make_gui()
    g.show_section("Statistics")
    g.stats_frame.grid.assert_called()


# ---------------------------------------------------------------------------
# FlowSnipGUI._clear_url_placeholder / _restore_url_placeholder
# ---------------------------------------------------------------------------


def test_clear_url_placeholder_matches():
    g = _make_gui()
    g.url_textbox.get.return_value = "Enter one media URL per line (YouTube, etc.)"
    g._clear_url_placeholder()
    g.url_textbox.delete.assert_called()


def test_clear_url_placeholder_no_match():
    g = _make_gui()
    g.url_textbox.get.return_value = "https://youtube.com/watch?v=abc"
    g._clear_url_placeholder()
    g.url_textbox.delete.assert_not_called()


def test_restore_url_placeholder_empty():
    g = _make_gui()
    g.url_textbox.get.return_value = ""
    g._restore_url_placeholder()
    g.url_textbox.insert.assert_called()


def test_restore_url_placeholder_has_content():
    g = _make_gui()
    g.url_textbox.get.return_value = "https://example.com"
    g._restore_url_placeholder()
    g.url_textbox.insert.assert_not_called()


# ---------------------------------------------------------------------------
# FlowSnipGUI._check_start_button_state
# ---------------------------------------------------------------------------


def test_check_start_button_state_with_urls():
    g = _make_gui()
    g.url_textbox.get.return_value = "https://example.com"
    g._check_start_button_state()
    g.start_button.configure.assert_called_with(state="normal", text="Start")


def test_check_start_button_state_placeholder():
    g = _make_gui()
    g.url_textbox.get.return_value = "Enter one video URL per line"
    g._check_start_button_state()
    g.start_button.configure.assert_not_called()


def test_check_start_button_state_empty():
    g = _make_gui()
    g.url_textbox.get.return_value = ""
    g._check_start_button_state()
    g.start_button.configure.assert_not_called()


# ---------------------------------------------------------------------------
# FlowSnipGUI.add_download
# ---------------------------------------------------------------------------


def test_add_download_empty_url():
    g = _make_gui()
    g.url_textbox.get.return_value = ""
    with patch("flowsnip.gui.messagebox.showwarning") as mock_warn:
        g.add_download()
    mock_warn.assert_called_once()


def test_add_download_placeholder():
    g = _make_gui()
    g.url_textbox.get.return_value = "Enter one video URL per line"
    with patch("flowsnip.gui.messagebox.showwarning") as mock_warn:
        g.add_download()
    mock_warn.assert_called_once()


def test_add_download_valid_url_auto_start():
    g = _make_gui()
    g.config.ui.auto_start_downloads = True
    g.download_manager.is_running = False
    g.url_textbox.get.return_value = "https://youtube.com/watch?v=abc"
    g.add_download()
    g.download_manager.add_download.assert_called_once_with(
        "https://youtube.com/watch?v=abc"
    )
    g.download_manager.start_downloads.assert_called_once()


def test_add_download_already_running():
    g = _make_gui()
    g.config.ui.auto_start_downloads = True
    g.download_manager.is_running = True
    g.url_textbox.get.return_value = "https://youtube.com/watch?v=abc"
    g.add_download()
    g.download_manager.start_downloads.assert_not_called()


def test_add_download_whitespace_only():
    g = _make_gui()
    g.url_textbox.get.return_value = "   \n   "
    with patch("flowsnip.gui.messagebox.showwarning") as mock_warn:
        g.add_download()
    mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.log_message
# ---------------------------------------------------------------------------


def test_log_message_under_limit():
    g = _make_gui()
    g.log_textbox.get.return_value = "line\n" * 500
    g.log_message("hello")
    g.log_textbox.configure.assert_called()


def test_log_message_over_limit():
    g = _make_gui()
    g._log_line_count = _LOG_LINE_LIMIT + 1
    g.log_message("hello")
    g.log_textbox.delete.assert_called()


# ---------------------------------------------------------------------------
# FlowSnipGUI.show_log_context_menu / copy_log_contents / clear_log
# ---------------------------------------------------------------------------


def test_show_log_context_menu():
    g = _make_gui()
    event = MagicMock()
    event.x_root = 100
    event.y_root = 200
    mock_menu = MagicMock()
    import tkinter

    orig_menu = getattr(tkinter, "Menu", None)
    tkinter.Menu = MagicMock(return_value=mock_menu)
    try:
        g.show_log_context_menu(event)
    finally:
        if orig_menu is not None:
            tkinter.Menu = orig_menu
        elif hasattr(tkinter, "Menu"):
            del tkinter.Menu


def test_copy_log_contents():
    g = _make_gui()
    g.log_textbox.get.return_value = "some log"
    g.copy_log_contents()
    g.root.clipboard_clear.assert_called()
    g.root.clipboard_append.assert_called_with("some log")


def test_clear_log():
    g = _make_gui()
    g.clear_log()
    g.log_textbox.delete.assert_called_with("1.0", "end")


# ---------------------------------------------------------------------------
# FlowSnipGUI.start_downloads
# ---------------------------------------------------------------------------


def test_start_downloads_with_urls_not_running():
    g = _make_gui()
    g.url_textbox.get.return_value = "https://youtube.com/watch?v=abc"
    g.download_manager.is_running = False

    def sync_thread(*, target=None, daemon=True, **kw):
        stub = MagicMock()
        stub.start = target or (lambda: None)
        return stub

    with patch("threading.Thread", side_effect=sync_thread):
        g.start_downloads()
    g.download_manager.add_multiple_downloads.assert_called_once()
    g.download_manager.start_downloads.assert_called_once()


def test_start_downloads_no_urls_not_running():
    g = _make_gui()
    g.url_textbox.get.return_value = ""
    g.download_manager.is_running = False
    g.start_downloads()
    g.download_manager.start_downloads.assert_called_once()


def test_start_downloads_already_running():
    g = _make_gui()
    g.url_textbox.get.return_value = ""
    g.download_manager.is_running = True
    g.start_downloads()
    g.download_manager.start_downloads.assert_not_called()


def test_start_downloads_placeholder_text():
    g = _make_gui()
    g.url_textbox.get.return_value = "Enter one video URL per line"
    g.download_manager.is_running = False
    g.start_downloads()
    g.download_manager.add_multiple_downloads.assert_not_called()
    g.download_manager.start_downloads.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.pause_downloads
# ---------------------------------------------------------------------------


def test_pause_downloads_when_running():
    g = _make_gui()
    g.download_manager.is_paused = False
    g.pause_downloads()
    g.download_manager.pause_downloads.assert_called_once()


def test_pause_downloads_when_paused():
    g = _make_gui()
    g.download_manager.is_paused = True
    g.pause_downloads()
    g.download_manager.resume_downloads.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.stop_downloads
# ---------------------------------------------------------------------------


def test_stop_downloads():
    g = _make_gui()

    def sync_thread(*, target=None, daemon=True, **kw):
        stub = MagicMock()
        stub.start = target or (lambda: None)
        return stub

    with patch("threading.Thread", side_effect=sync_thread):
        g.stop_downloads()
    g.download_manager.stop_downloads.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.open_downloads_folder
# ---------------------------------------------------------------------------


def test_open_downloads_folder_windows():
    g = _make_gui()
    with (
        patch("platform.system", return_value="Windows"),
        patch("subprocess.run") as mock_run,
    ):
        g.open_downloads_folder()
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][0] == "explorer"


def test_open_downloads_folder_mac():
    g = _make_gui()
    with (
        patch("platform.system", return_value="Darwin"),
        patch("subprocess.run") as mock_run,
    ):
        g.open_downloads_folder()
    assert mock_run.call_args[0][0][0] == "open"


def test_open_downloads_folder_linux():
    g = _make_gui()
    with (
        patch("platform.system", return_value="Linux"),
        patch("subprocess.run") as mock_run,
    ):
        g.open_downloads_folder()
    assert mock_run.call_args[0][0][0] == "xdg-open"


def test_open_downloads_folder_error():
    g = _make_gui()
    with (
        patch("platform.system", return_value="Windows"),
        patch("subprocess.run", side_effect=OSError("nope")),
        patch("flowsnip.gui.messagebox.showerror") as mock_err,
    ):
        g.open_downloads_folder()
    mock_err.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.update_button_states
# ---------------------------------------------------------------------------


def test_update_button_states_running_not_paused():
    g = _make_gui()
    g.download_manager.is_running = True
    g.download_manager.is_paused = False
    g.update_button_states()
    g.pause_button.configure.assert_called_with(text="Pause")


def test_update_button_states_running_paused():
    g = _make_gui()
    g.download_manager.is_running = True
    g.download_manager.is_paused = True
    g.update_button_states()
    g.pause_button.configure.assert_called_with(text="Resume")


def test_update_button_states_not_running():
    g = _make_gui()
    g.download_manager.is_running = False
    g.update_button_states()
    g.start_button.configure.assert_called_with(state="normal")


def test_update_button_states_running_with_pending_url_keeps_start_enabled():
    """A progress tick while downloads are running must not clobber a pending URL."""
    g = _make_gui()
    g.download_manager.is_running = True
    g.download_manager.is_paused = False
    g.url_textbox.get.return_value = "https://example.com"
    g.update_button_states()
    g.start_button.configure.assert_called_with(state="normal", text="Start")


def test_update_button_states_running_no_pending_url_disables_start():
    g = _make_gui()
    g.download_manager.is_running = True
    g.download_manager.is_paused = False
    g.url_textbox.get.return_value = ""
    g.update_button_states()
    g.start_button.configure.assert_called_with(state="disabled", text="Start")


# ---------------------------------------------------------------------------
# FlowSnipGUI.progress_callback / _update_ui_callback
# ---------------------------------------------------------------------------


def test_progress_callback_schedules_after():
    g = _make_gui()
    g.progress_callback("download_added", MagicMock())
    g.root.after.assert_called()


def test_progress_callback_throttled():
    g = _make_gui()
    item = _make_item()
    g._last_ui_update = {item.id: 0.95}  # 1.0 - 0.95 = 0.05 s < 0.1 s threshold
    g.root.after.reset_mock()
    with patch("flowsnip.gui.time.monotonic", return_value=1.0):
        g.progress_callback("download_progress", item)
    g.root.after.assert_not_called()


def test_progress_callback_not_throttled_stale():
    g = _make_gui()
    item = _make_item()
    g._last_ui_update = {item.id: 0.5}  # 1.0 - 0.5 = 0.5 s > 0.1 s threshold
    g.root.after.reset_mock()
    with patch("flowsnip.gui.time.monotonic", return_value=1.0):
        g.progress_callback("download_progress", item)
    g.root.after.assert_called()
    assert g._last_ui_update[item.id] == 1.0


def test_update_ui_callback_download_added():
    g = _make_gui()
    item = _make_item()
    with (
        patch.object(g, "add_progress_frame") as mock_add,
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_added", item)
    mock_add.assert_called_once_with(item)


def test_update_ui_callback_download_progress():
    g = _make_gui()
    item = _make_item()
    with (
        patch.object(g, "update_progress_frame") as mock_upd,
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_progress", item)
    mock_upd.assert_called_once_with(item)


def test_update_ui_callback_download_cancelled():
    g = _make_gui()
    item = _make_item()
    with (
        patch.object(g, "remove_progress_frame") as mock_rem,
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_cancelled", item)
    mock_rem.assert_called_once_with(item.id)


def test_update_ui_callback_download_removed():
    g = _make_gui()
    with (
        patch.object(g, "remove_progress_frame") as mock_rem,
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_removed", {"id": "abc123"})
    mock_rem.assert_called_once_with("abc123")


def test_update_ui_callback_log_message():
    g = _make_gui()
    with (
        patch.object(g, "log_message") as mock_log,
        patch.object(g, "update_status_display") as mock_status,
        patch.object(g, "update_button_states") as mock_btn,
    ):
        g._update_ui_callback("log_message", {"message": "hello"})
    mock_log.assert_called_once_with("hello")
    mock_status.assert_not_called()
    mock_btn.assert_not_called()


def test_update_ui_callback_other_events():
    g = _make_gui()
    item = _make_item()
    for event in ["download_started", "download_completed", "download_failed"]:
        with (
            patch.object(g, "update_progress_frame"),
            patch.object(g, "update_status_display") as mock_status,
            patch.object(g, "update_button_states") as mock_btn,
        ):
            g._update_ui_callback(event, item)
        mock_status.assert_called()
        mock_btn.assert_called()


def test_update_ui_callback_skipped_schedules_auto_remove():
    g = _make_gui()
    item = _make_item(status=DownloadStatus.SKIPPED)
    with (
        patch.object(g, "update_progress_frame"),
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_completed", item)
    after_calls = [
        c for c in g.root.after.call_args_list if c[0][0] == _AUTO_REMOVE_DELAY_MS
    ]
    assert len(after_calls) == 1


def test_update_ui_callback_completed_auto_remove_enabled():
    g = _make_gui()
    g.config.ui.auto_remove_completed = True
    item = _make_item(status=DownloadStatus.COMPLETED)
    with (
        patch.object(g, "update_progress_frame"),
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_completed", item)
    after_calls = [
        c for c in g.root.after.call_args_list if c[0][0] == _AUTO_REMOVE_DELAY_MS
    ]
    assert len(after_calls) == 1


def test_update_ui_callback_completed_auto_remove_disabled():
    g = _make_gui()
    g.config.ui.auto_remove_completed = False
    item = _make_item(status=DownloadStatus.COMPLETED)
    with (
        patch.object(g, "update_progress_frame"),
        patch.object(g, "update_status_display"),
        patch.object(g, "update_button_states"),
    ):
        g._update_ui_callback("download_completed", item)
    after_calls = [
        c for c in g.root.after.call_args_list if c[0][0] == _AUTO_REMOVE_DELAY_MS
    ]
    assert len(after_calls) == 0


# ---------------------------------------------------------------------------
# FlowSnipGUI.add_progress_frame
# ---------------------------------------------------------------------------


def test_add_progress_frame_new():
    g = _make_gui()
    item = _make_item()
    g.progress_frames = {}
    g.add_progress_frame(item)
    assert item.id in g.progress_frames


def test_add_progress_frame_duplicate():
    g = _make_gui()
    item = _make_item()
    mock_frame = MagicMock()
    g.progress_frames = {item.id: mock_frame}
    g.add_progress_frame(item)
    assert g.progress_frames[item.id] is mock_frame


def test_add_progress_frame_no_status_label():
    g = _make_gui()
    item = _make_item()
    del g.status_label
    g.add_progress_frame(item)
    assert item.id in g.progress_frames


def test_add_progress_frame_status_label_gone():
    g = _make_gui()
    item = _make_item()
    g.status_label.winfo_exists.return_value = False
    g.add_progress_frame(item)
    assert item.id in g.progress_frames


# ---------------------------------------------------------------------------
# FlowSnipGUI.update_progress_frame
# ---------------------------------------------------------------------------


def test_update_progress_frame_exists():
    g = _make_gui()
    item = _make_item()
    mock_frame = MagicMock()
    g.progress_frames = {item.id: mock_frame}
    g.update_progress_frame(item)
    mock_frame.update_progress.assert_called_once_with(item)


def test_update_progress_frame_not_found():
    g = _make_gui()
    item = _make_item()
    g.progress_frames = {}
    g.update_progress_frame(item)


# ---------------------------------------------------------------------------
# FlowSnipGUI.remove_progress_frame
# ---------------------------------------------------------------------------


def test_remove_progress_frame_found_no_remaining():
    g = _make_gui()
    item = _make_item()
    mock_frame = MagicMock()
    g.progress_frames = {item.id: mock_frame}
    g.remove_progress_frame(item.id)
    mock_frame.destroy.assert_called_once()
    assert item.id not in g.progress_frames
    assert hasattr(g, "status_label")


def test_remove_progress_frame_found_remaining():
    g = _make_gui()
    item1 = _make_item()
    item2 = _make_item()
    item2.id = "other-id"
    mock1 = MagicMock()
    mock2 = MagicMock()
    g.progress_frames = {item1.id: mock1, item2.id: mock2}
    g.remove_progress_frame(item1.id)
    mock1.destroy.assert_called_once()
    assert item1.id not in g.progress_frames
    mock2.grid.assert_called()


def test_remove_progress_frame_not_found():
    g = _make_gui()
    g.progress_frames = {}
    g.remove_progress_frame("nonexistent")


# ---------------------------------------------------------------------------
# FlowSnipGUI.update_status_display
# ---------------------------------------------------------------------------


def test_update_status_display_active():
    g = _make_gui()
    g.download_manager.get_queue_status.return_value = {
        "active_count": 2,
        "pending_count": 0,
        "completed_count": 0,
        "failed_count": 0,
    }
    g.update_status_display()
    g.root.title.assert_called_with("FlowSnip - 2 downloading")


def test_update_status_display_idle():
    g = _make_gui()
    g.download_manager.get_queue_status.return_value = {
        "active_count": 0,
        "pending_count": 0,
        "completed_count": 0,
        "failed_count": 0,
    }
    g.update_status_display()
    g.root.title.assert_called_with("FlowSnip - Media Downloader")


# ---------------------------------------------------------------------------
# FlowSnipGUI.update_stats
# ---------------------------------------------------------------------------


def test_update_stats():
    g = _make_gui()
    g.download_manager.get_queue_status.return_value = {
        "active_count": 1,
        "pending_count": 2,
        "completed_count": 3,
        "failed_count": 4,
    }
    g.update_stats()
    g.stats_labels["active"].configure.assert_called_with(text="1")
    g.stats_labels["completed"].configure.assert_called_with(text="3")
    g.stats_labels["failed"].configure.assert_called_with(text="4")
    g.stats_labels["total"].configure.assert_called_with(text="10")
    g.root.after.assert_called_with(_STATS_POLL_ACTIVE_MS, g.update_stats)  # active


def test_update_stats_idle():
    g = _make_gui()
    g.download_manager.get_queue_status.return_value = {
        "active_count": 0,
        "pending_count": 0,
        "completed_count": 0,
        "failed_count": 0,
    }
    g.update_stats()
    g.root.after.assert_called_with(_STATS_POLL_IDLE_MS, g.update_stats)  # idle


# ---------------------------------------------------------------------------
# FlowSnipGUI.run
# ---------------------------------------------------------------------------


def test_run_normal():
    g = _make_gui()
    g.run()
    g.root.protocol.assert_called()
    g.root.mainloop.assert_called()


def test_run_exception():
    g = _make_gui()
    g.root.mainloop.side_effect = RuntimeError("crash")
    with patch.object(g, "cleanup") as mock_cleanup:
        g.run()
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.on_closing
# ---------------------------------------------------------------------------


def test_on_closing_normal():
    g = _make_gui()
    g.root.geometry.return_value = "1000x700+50+50"
    g.download_manager.active_downloads = {}
    g.on_closing()
    g.root.destroy.assert_called_once()
    assert g.config.ui.window_width == 1000
    assert g.config.ui.window_height == 700


def test_on_closing_geometry_no_x():
    g = _make_gui()
    g.root.geometry.return_value = None
    g.download_manager.active_downloads = {}
    g.on_closing()
    g.root.destroy.assert_called_once()


def test_on_closing_exception_in_body():
    g = _make_gui()
    g.download_manager.active_downloads = {"id1": MagicMock()}
    g.download_manager.cancel_download.side_effect = RuntimeError("oops")
    g.on_closing()
    g.root.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI.cleanup
# ---------------------------------------------------------------------------


def test_cleanup_with_manager():
    g = _make_gui()
    g.cleanup()
    g.download_manager.stop_downloads.assert_called_once()


def test_cleanup_no_manager():
    g = _make_gui()
    del g.download_manager
    g.cleanup()


# ---------------------------------------------------------------------------
# ConfigFrame — update settings callbacks
# ---------------------------------------------------------------------------


def test_update_auto_remove_completed_true():
    cf = _make_config_frame()
    cf.auto_remove_completed_var.set(True)
    cf.update_auto_remove_completed()
    assert cf.config_obj.ui.auto_remove_completed is True


def test_update_auto_remove_completed_false():
    cf = _make_config_frame()
    cf.auto_remove_completed_var.set(False)
    cf.update_auto_remove_completed()
    assert cf.config_obj.ui.auto_remove_completed is False


def test_update_ui_from_config_auto_remove_completed():
    cf = _make_config_frame()
    cf.config_obj.ui.auto_remove_completed = True
    cf.update_ui_from_config()
    assert cf.auto_remove_completed_var.get() is True


def test_update_ui_from_config_embed_subs():
    cf = _make_config_frame()
    cf.config_obj.ytdl.embed_subs = False
    cf.update_ui_from_config()
    assert cf.embed_subs_var.get() is False


def test_update_check_flowsnip():
    cf = _make_config_frame()
    cf.check_flowsnip_var.set(False)
    cf.update_check_flowsnip()
    assert cf.config_obj.updates.check_flowsnip is False


def test_update_check_ytdlp():
    cf = _make_config_frame()
    cf.check_ytdlp_var.set(False)
    cf.update_check_ytdlp()
    assert cf.config_obj.updates.check_ytdlp is False


def test_update_check_frequency():
    cf = _make_config_frame()
    cf.update_check_frequency("weekly")
    assert cf.config_obj.updates.frequency == "weekly"


# ---------------------------------------------------------------------------
# FlowSnipGUI — update banner
# ---------------------------------------------------------------------------


def test_setup_update_banner():
    g = _make_gui()
    g._setup_update_banner()
    assert hasattr(g, "_update_banner")
    assert hasattr(g, "_update_banner_label")
    assert hasattr(g, "_update_banner_action")


def test_show_update_banner():
    g = _make_gui()
    # _make_gui already provides _update_banner/_update_banner_label/_update_banner_action
    # as MagicMocks — do NOT call _setup_update_banner() here or it overwrites them.
    cb = MagicMock()
    g.show_update_banner("New version available", "Download", cb)
    g._update_banner.grid.assert_called()


def test_dismiss_update_banner():
    g = _make_gui()
    g._dismiss_update_banner()
    g._update_banner.grid_remove.assert_called_once()


# ---------------------------------------------------------------------------
# FlowSnipGUI._set_window_icon
# ---------------------------------------------------------------------------


def test_set_window_icon_windows_file_exists():
    g = _make_gui()
    with (
        patch("flowsnip.gui.platform.system", return_value="Windows"),
        patch("flowsnip.gui._resource_path") as mock_rp,
    ):
        p = MagicMock()
        p.exists.return_value = True
        mock_rp.return_value = p
        g._set_window_icon()
    g.root.wm_iconbitmap.assert_called_once()


def test_set_window_icon_windows_file_missing():
    g = _make_gui()
    with (
        patch("flowsnip.gui.platform.system", return_value="Windows"),
        patch("flowsnip.gui._resource_path") as mock_rp,
    ):
        p = MagicMock()
        p.exists.return_value = False
        mock_rp.return_value = p
        g._set_window_icon()
    g.root.wm_iconbitmap.assert_not_called()


def test_set_window_icon_other_platform():
    g = _make_gui()
    mock_img = MagicMock()
    with (
        patch("flowsnip.gui.platform.system", return_value="Linux"),
        patch("flowsnip.gui._resource_path") as mock_rp,
        patch("PIL.Image.open", return_value=MagicMock()),
        patch("PIL.ImageTk.PhotoImage", return_value=mock_img),
    ):
        p = MagicMock()
        p.exists.return_value = True
        mock_rp.return_value = p
        g._set_window_icon()
    g.root.iconphoto.assert_called_once()
    assert g._icon_ref is mock_img


def test_set_window_icon_other_platform_no_file():
    g = _make_gui()
    with (
        patch("flowsnip.gui.platform.system", return_value="Darwin"),
        patch("flowsnip.gui._resource_path") as mock_rp,
    ):
        p = MagicMock()
        p.exists.return_value = False
        mock_rp.return_value = p
        g._set_window_icon()
    g.root.iconphoto.assert_not_called()


def test_set_window_icon_exception_swallowed():
    g = _make_gui()
    with (
        patch("flowsnip.gui.platform.system", return_value="Windows"),
        patch("flowsnip.gui._resource_path") as mock_rp,
    ):
        p = MagicMock()
        p.exists.return_value = True
        mock_rp.return_value = p
        g.root.wm_iconbitmap.side_effect = Exception("no display")
        g._set_window_icon()  # must not raise


# ---------------------------------------------------------------------------
# Branch coverage — edge cases
# ---------------------------------------------------------------------------


def test_show_section_unknown():
    g = _make_gui()
    g.show_section("Unknown")  # no match — all sections hidden, no crash


def test_flowsnipgui_init_no_auto_start(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir
    config.ui.auto_start_downloads = False
    with patch("flowsnip.gui.DownloadManager") as MockDM:
        mock_dm = MagicMock()
        mock_dm.is_running = False
        mock_dm.is_paused = False
        mock_dm.get_queue_status.return_value = {
            "active_count": 0,
            "pending_count": 0,
            "completed_count": 0,
            "failed_count": 0,
        }
        MockDM.return_value = mock_dm
        FlowSnipGUI(config)
    mock_dm.start_downloads.assert_not_called()


def test_update_ui_callback_unhandled_event():
    g = _make_gui()
    with (
        patch.object(g, "update_status_display") as mock_status,
        patch.object(g, "update_button_states") as mock_btn,
    ):
        g._update_ui_callback("downloads_paused", None)
    mock_status.assert_called()
    mock_btn.assert_called()
