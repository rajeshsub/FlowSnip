"""Tests for flowsnip/download_manager.py - targets 100% line coverage."""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ytdlp_formats import ADAPTIVE_4K, HLS_ONLY_1080, fmt, select

from flowsnip.download_manager import (
    _UNSET,
    MAX_HISTORY,
    DownloadItem,
    DownloadManager,
    DownloadStatus,
    _find_js_runtime,
    _get_js_runtime,
    _get_yt_dlp,
    _height_to_label,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ytdl(
    *,
    raise_on_download=None,
    raise_on_extract=None,
    title="Test Video",
    progress_data=None,
    log_messages=None,
):
    """Return a side_effect factory for yt_dlp.YoutubeDL that captures opts."""
    captured = {}

    def constructor(opts):
        captured["opts"] = opts
        instance = MagicMock()
        instance.__enter__ = lambda s: instance
        instance.__exit__ = MagicMock(return_value=False)

        def fake_download(urls):
            # Call logger with requested messages
            if log_messages:
                logger = opts.get("logger")
                if logger:
                    for msg in log_messages:
                        logger.debug(msg)
            # Fire progress hooks
            for hook_data in progress_data or []:
                for hook in opts.get("progress_hooks", []):
                    hook(hook_data)
            if raise_on_download:
                raise raise_on_download

        instance.download = fake_download

        if raise_on_extract:
            instance.extract_info = MagicMock(side_effect=raise_on_extract)
        else:
            instance.extract_info = MagicMock(return_value={"title": title})

        return instance

    constructor.captured = captured
    return constructor


def _run_worker(manager, item, ytdl_side_effect):
    """Patch yt_dlp and run _download_worker; return captured opts."""
    factory = ytdl_side_effect
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        manager._download_worker(item)
    return factory.captured.get("opts", {})


# ---------------------------------------------------------------------------
# _find_js_runtime
# ---------------------------------------------------------------------------


def test_find_js_runtime_node_on_path():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": ""}),
        patch(
            "shutil.which",
            side_effect=lambda n: "/usr/bin/node" if n == "node" else None,
        ),
    ):
        result = _find_js_runtime()
    assert result == {"node": {"path": "/usr/bin/node"}}


def test_find_js_runtime_nodejs_on_path():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": ""}),
        patch(
            "shutil.which",
            side_effect=lambda n: "/usr/bin/nodejs" if n == "nodejs" else None,
        ),
    ):
        result = _find_js_runtime()
    assert result == {"node": {"path": "/usr/bin/nodejs"}}


def test_find_js_runtime_common_windows_path():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": ""}),
        patch("shutil.which", return_value=None),
        patch("os.path.exists", side_effect=lambda p: "nodejs" in p),
    ):
        result = _find_js_runtime()
    assert result is not None and "node" in result


def test_find_js_runtime_deno_fallback():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": ""}),
        patch(
            "shutil.which",
            side_effect=lambda n: "/usr/bin/deno" if n == "deno" else None,
        ),
        patch("os.path.exists", return_value=False),
    ):
        result = _find_js_runtime()
    assert result == {"deno": {"path": "/usr/bin/deno"}}


def test_find_js_runtime_nothing_found():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": ""}),
        patch("shutil.which", return_value=None),
        patch("os.path.exists", return_value=False),
    ):
        result = _find_js_runtime()
    assert result is None


def test_find_js_runtime_env_var_set(tmp_path):
    fake_node = tmp_path / "node"
    fake_node.write_text("")
    with patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": str(fake_node)}):
        result = _find_js_runtime()
    assert result == {"node": {"path": str(fake_node)}}


def test_find_js_runtime_env_var_nonexistent():
    with (
        patch.dict(os.environ, {"FLOWSNIP_NODE_PATH": "/nonexistent/node"}),
        patch("shutil.which", return_value=None),
        patch("os.path.exists", return_value=False),
    ):
        result = _find_js_runtime()
    assert result is None


# ---------------------------------------------------------------------------
# DownloadStatus / DownloadItem
# ---------------------------------------------------------------------------


def test_download_status_values():
    assert DownloadStatus.PENDING.value == "pending"
    assert DownloadStatus.DOWNLOADING.value == "downloading"
    assert DownloadStatus.COMPLETED.value == "completed"
    assert DownloadStatus.FAILED.value == "failed"
    assert DownloadStatus.PAUSED.value == "paused"
    assert DownloadStatus.CANCELLED.value == "cancelled"


def test_download_item_defaults():
    item = DownloadItem()
    assert item.url == ""
    assert item.status == DownloadStatus.PENDING
    assert item.progress == 0.0
    assert item.retry_count == 0
    assert item.output_path is None


# ---------------------------------------------------------------------------
# DownloadManager.is_valid_url
# ---------------------------------------------------------------------------


def test_is_valid_url_https():
    assert DownloadManager.is_valid_url("https://www.youtube.com/watch?v=test") is True


def test_is_valid_url_http():
    assert DownloadManager.is_valid_url("http://example.com/video") is True


def test_is_valid_url_no_scheme():
    assert DownloadManager.is_valid_url("www.youtube.com/watch?v=test") is False


def test_is_valid_url_empty():
    assert DownloadManager.is_valid_url("") is False


# ---------------------------------------------------------------------------
# DownloadManager init
# ---------------------------------------------------------------------------


def test_init_creates_manager(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    assert not mgr.is_running
    assert not mgr.is_paused
    mgr.stop_downloads()


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------


def test_extract_title_with_browser_cookies_success(download_manager):
    download_manager.config.download.cookies_from_browser = "chrome"
    factory = _make_ytdl(title="My Video")
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "My Video"
    download_manager.config.download.cookies_from_browser = None


def test_extract_title_with_browser_cookies_fail_falls_through(download_manager):
    download_manager.config.download.cookies_from_browser = "chrome"
    call_count = [0]

    def factory(opts):
        call_count[0] += 1
        instance = MagicMock()
        instance.__enter__ = lambda s: instance
        instance.__exit__ = MagicMock(return_value=False)
        if call_count[0] == 1:
            instance.extract_info = MagicMock(side_effect=Exception("boom"))
        else:
            instance.extract_info = MagicMock(return_value={"title": "Fallback"})
        return instance

    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "Fallback"
    download_manager.config.download.cookies_from_browser = None


def test_extract_title_no_cookies_success(download_manager):
    factory = _make_ytdl(title="Public Video")
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "Public Video"


def test_extract_title_with_cookie_file(download_manager):
    download_manager.config.download.cookies_file = "/tmp/cookies.txt"
    factory = _make_ytdl(title="Auth Video")
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "Auth Video"
    assert factory.captured["opts"].get("cookiefile") == "/tmp/cookies.txt"
    download_manager.config.download.cookies_file = None


def test_extract_title_all_fail(download_manager):
    def factory(opts):
        instance = MagicMock()
        instance.__enter__ = lambda s: instance
        instance.__exit__ = MagicMock(return_value=False)
        instance.extract_info = MagicMock(side_effect=Exception("network error"))
        return instance

    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result.startswith("__error__:")


def test_extract_title_no_js_runtime(download_manager):
    with patch("flowsnip.download_manager._get_js_runtime", return_value=None):
        factory = _make_ytdl(title="Video")
        with patch("yt_dlp.YoutubeDL", side_effect=factory):
            result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "Video"
    assert "js_runtimes" not in factory.captured.get("opts", {})


# ---------------------------------------------------------------------------
# add_download / add_multiple_downloads
# ---------------------------------------------------------------------------


def test_add_download_invalid_url(download_manager, mock_callback):
    result = download_manager.add_download("not-a-url")
    assert result == ""
    mock_callback.assert_called_with(
        "log_message", {"message": "Invalid or unsupported URL: not-a-url"}
    )


def test_add_download_valid_url(download_manager):
    factory = _make_ytdl(title="My Video")
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager.add_download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
    assert result != ""
    assert download_manager.pending_queue.qsize() == 1


def test_add_download_title_error_uses_url_fragment(download_manager):
    factory = _make_ytdl(raise_on_extract=Exception("fail"))
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = download_manager.add_download("https://www.youtube.com/watch?v=ABC123")
    assert result != ""
    item = download_manager.pending_queue.get_nowait()
    assert "ABC123" in item.title or item.title == "Unknown Video"


def test_add_download_no_callback(test_config):
    mgr = DownloadManager(test_config, None)
    factory = _make_ytdl(title="Video")
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        result = mgr.add_download("https://www.youtube.com/watch?v=test")
    assert result != ""
    mgr.stop_downloads()


def test_add_multiple_downloads(download_manager):
    factory = _make_ytdl(title="Video")
    urls = [
        "https://www.youtube.com/watch?v=AAA",
        "not-valid",
        "https://www.youtube.com/watch?v=BBB",
    ]
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        ids = download_manager.add_multiple_downloads(urls)
    assert len(ids) == 2  # invalid URL is skipped


# ---------------------------------------------------------------------------
# start / pause / resume / stop
# ---------------------------------------------------------------------------


def test_start_downloads(download_manager):
    download_manager.start_downloads()
    assert download_manager.is_running
    assert not download_manager.is_paused


def test_start_downloads_idempotent(download_manager):
    download_manager.start_downloads()
    download_manager.start_downloads()  # second call is no-op
    assert download_manager.is_running


def test_pause_resume(download_manager, mock_callback):
    download_manager.start_downloads()
    download_manager.pause_downloads()
    assert download_manager.is_paused
    mock_callback.assert_any_call("downloads_paused", None)

    download_manager.resume_downloads()
    assert not download_manager.is_paused
    mock_callback.assert_any_call("downloads_resumed", None)


def test_stop_downloads(download_manager, mock_callback):
    download_manager.start_downloads()
    download_manager.stop_downloads()
    assert not download_manager.is_running
    mock_callback.assert_any_call("downloads_stopped", None)


def test_stop_downloads_without_callback(test_config):
    mgr = DownloadManager(test_config, None)
    mgr.start_downloads()
    mgr.stop_downloads()  # should not raise


def test_stop_downloads_cancels_active_tasks(download_manager):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    future = MagicMock()
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future
    download_manager.stop_downloads()
    future.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# cancel_download
# ---------------------------------------------------------------------------


def test_cancel_download_active_with_task(download_manager, mock_callback):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    future = MagicMock()
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future

    download_manager.cancel_download(item.id)

    future.cancel.assert_called_once()
    assert item.id not in download_manager.active_downloads
    assert item.id not in download_manager.download_tasks
    assert item.status == DownloadStatus.CANCELLED
    mock_callback.assert_any_call("download_cancelled", item)


def test_cancel_download_active_without_task(download_manager):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    download_manager.active_downloads[item.id] = item
    # no corresponding future
    download_manager.cancel_download(item.id)
    assert item.id not in download_manager.active_downloads


def test_cancel_download_not_active(download_manager):
    # Should be a no-op
    download_manager.cancel_download("nonexistent-id")


# ---------------------------------------------------------------------------
# retry_download
# ---------------------------------------------------------------------------


def test_retry_download_found(download_manager, mock_callback):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    item.status = DownloadStatus.FAILED
    download_manager.failed_downloads.append(item)

    download_manager.retry_download(item.id)

    assert item not in download_manager.failed_downloads
    assert download_manager.pending_queue.qsize() == 1
    assert item.status == DownloadStatus.PENDING
    mock_callback.assert_any_call("download_retried", item)


def test_retry_download_not_found(download_manager):
    # Should be a no-op
    download_manager.retry_download("nonexistent-id")


# ---------------------------------------------------------------------------
# remove_download
# ---------------------------------------------------------------------------


def test_remove_download_from_failed(download_manager, mock_callback):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    download_manager.failed_downloads.append(item)
    download_manager.remove_download(item.id, from_queue="failed")
    assert item not in download_manager.failed_downloads
    mock_callback.assert_any_call(
        "download_removed", {"id": item.id, "queue": "failed"}
    )


def test_remove_download_from_completed(download_manager, mock_callback):
    item = DownloadItem(url="https://youtube.com/watch?v=x", title="T")
    download_manager.completed_downloads.append(item)
    download_manager.remove_download(item.id, from_queue="completed")
    assert item not in download_manager.completed_downloads


# ---------------------------------------------------------------------------
# move_download_up / move_download_down (pass-through stubs)
# ---------------------------------------------------------------------------


def test_move_download_up_is_noop(download_manager):
    download_manager.move_download_up("any-id")


def test_move_download_down_is_noop(download_manager):
    download_manager.move_download_down("any-id")


# ---------------------------------------------------------------------------
# get_queue_status
# ---------------------------------------------------------------------------


def test_get_queue_status(download_manager):
    status = download_manager.get_queue_status()
    expected = {
        "pending_count",
        "active_count",
        "completed_count",
        "failed_count",
        "is_running",
        "is_paused",
        "active_downloads",
        "failed_downloads",
        "completed_downloads",
    }
    assert expected.issubset(status.keys())
    assert status["pending_count"] == 0
    assert status["is_running"] is False


# ---------------------------------------------------------------------------
# _download_worker - access modes (signed in / signed out / cookie file)
# ---------------------------------------------------------------------------

_BEST = "bestvideo+bestaudio/best"
_LOGIN_HINT = "requires YouTube login"


def _mode_of(opts):
    if "cookiesfrombrowser" in opts:
        return "browser"
    if "cookiefile" in opts:
        return "file"
    return "public"


def _fake_sessions(
    *, infos=None, extract_errors=None, download_errors=None, close_errors=None
):
    """Fake yt_dlp.YoutubeDL keyed by access mode.

    infos: mode -> processed info dict returned by extract_info.
    extract_errors / download_errors / close_errors: mode -> exception to raise
    from the probe, from any download call, or from close().
    Records the opts per mode, every extraction, downloads in order, and closes.
    """
    record = {
        "opts": {},
        "all_opts": [],
        "extract_calls": [],
        "downloaded": [],
        "url_downloads": [],
        "closed": [],
    }

    def constructor(opts):
        mode = _mode_of(opts)
        record["opts"][mode] = opts
        record["all_opts"].append(opts)
        session = MagicMock()

        def fake_download(info):
            if mode in (download_errors or {}):
                raise download_errors[mode]
            for part in info.get("requested_formats") or [info]:
                for hook in opts["progress_hooks"]:
                    hook({"status": "finished", "filename": "out", "info_dict": part})
            record["downloaded"].append(mode)
            return info

        def extract_info(url, download=True):
            record["extract_calls"].append((mode, download))
            if not download and mode in (extract_errors or {}):
                raise extract_errors[mode]
            info = (infos or {}).get(mode, {"title": "Test Video"})
            return fake_download(info) if download else info

        def process_ie_result(info, download=True):
            assert download is True
            return fake_download(info)

        def download(urls):
            if mode in (download_errors or {}):
                raise download_errors[mode]
            record["url_downloads"].append((mode, list(urls), opts))

        def close():
            record["closed"].append(mode)
            if mode in (close_errors or {}):
                raise close_errors[mode]

        session.extract_info = extract_info
        session.process_ie_result = process_ie_result
        session.download = download
        session.close = close
        return session

    constructor.record = record
    return constructor


def _work(manager, item, sessions):
    with patch("yt_dlp.YoutubeDL", side_effect=sessions):
        manager._download_worker(item)
    return sessions.record


def _logged(mock_callback):
    return [
        c.args[1]["message"]
        for c in mock_callback.call_args_list
        if c.args[0] == "log_message"
    ]


def test_worker_without_cookies_probes_once_and_downloads_that_session(
    download_manager, sample_item
):
    sessions = _fake_sessions(infos={"public": select(_BEST, ADAPTIVE_4K)})
    record = _work(download_manager, sample_item, sessions)
    assert list(record["opts"]) == ["public"]
    assert record["extract_calls"] == [("public", False)]
    assert record["downloaded"] == ["public"]
    assert sample_item.resolution == "4K"


def test_worker_prefers_signed_out_4k_over_signed_in_1080p_hls(
    download_manager, sample_item
):
    # The reported bug: signed-in clients only offered pre-merged 1080p HLS.
    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]
    assert sample_item.resolution == "4K"


def test_worker_prefers_signed_in_when_it_offers_higher_resolution(
    download_manager, sample_item
):
    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, ADAPTIVE_4K),
            "public": select(_BEST, HLS_ONLY_1080),
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["browser"]


def test_worker_keeps_signed_in_on_equal_rank_without_quality_log(
    download_manager, sample_item, mock_callback
):
    download_manager.config.download.cookies_from_browser = "firefox"
    same = select(_BEST, ADAPTIVE_4K)
    sessions = _fake_sessions(infos={"browser": same, "public": same})
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["browser"]
    assert not [m for m in _logged(mock_callback) if m.startswith("Quality check")]


@pytest.mark.parametrize(
    "signed_in, signed_out",
    [
        ({"fps": 30, "tbr": 9000}, {"fps": 60, "tbr": 4000}),  # fps beats bitrate
        ({"fps": 30, "tbr": 4000}, {"fps": 30, "tbr": 9000}),  # then bitrate
    ],
)
def test_worker_breaks_height_ties_by_fps_then_bitrate(
    download_manager, sample_item, signed_in, signed_out
):
    download_manager.config.download.cookies_from_browser = "firefox"
    base = {"title": "Test Video", "height": 1080, "width": 1920}
    sessions = _fake_sessions(
        infos={"browser": {**base, **signed_in}, "public": {**base, **signed_out}}
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]


def test_worker_uses_signed_in_when_signed_out_fails_with_unrecognised_error(
    download_manager, sample_item
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={"browser": select(_BEST, ADAPTIVE_4K)},
        extract_errors={
            "public": DownloadError(
                "Join this channel to get access to members-only content"
            )
        },
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["browser"]


def test_worker_cookie_db_error_is_explained_and_signed_out_used(
    download_manager, sample_item, mock_callback
):
    download_manager.config.download.cookies_from_browser = "chrome"
    sessions = _fake_sessions(
        infos={"public": select(_BEST, ADAPTIVE_4K)},
        extract_errors={"browser": Exception("could not copy chrome cookie database")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]
    assert (
        "Could not extract cookies from chrome (close the browser and try again). "
        "Falling back..."
    ) in _logged(mock_callback)


def test_worker_cookie_file_wins_when_it_is_the_only_mode_that_extracts(
    download_manager, sample_item
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_file = "/tmp/cookies.txt"
    sessions = _fake_sessions(
        infos={"file": select(_BEST, ADAPTIVE_4K)},
        extract_errors={"public": DownloadError("Sign in to confirm your age")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["opts"]["file"]["cookiefile"] == "/tmp/cookies.txt"
    assert record["downloaded"] == ["file"]


def test_worker_all_modes_fail_with_auth_error_and_no_cookie_source_hints_login(
    download_manager, sample_item
):
    from yt_dlp.utils import DownloadError

    sessions = _fake_sessions(
        extract_errors={"public": DownloadError("Sign in to confirm you're not a bot")}
    )
    with pytest.raises(Exception, match=_LOGIN_HINT):
        _work(download_manager, sample_item, sessions)


def test_worker_all_modes_fail_names_each_mode(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        extract_errors={
            "browser": DownloadError("tv client unplayable"),
            "public": DownloadError("network timeout xyz"),
        }
    )
    with pytest.raises(Exception, match="yt-dlp error") as err:
        _work(download_manager, sample_item, sessions)
    assert "signed in via firefox: tv client unplayable" in str(err.value)
    assert "signed out: network timeout xyz" in str(err.value)
    assert _LOGIN_HINT not in str(err.value)


def test_worker_single_mode_failure_keeps_plain_error(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    sessions = _fake_sessions(
        extract_errors={"public": DownloadError("network timeout xyz")}
    )
    with pytest.raises(Exception, match=r"^yt-dlp error: network timeout xyz$"):
        _work(download_manager, sample_item, sessions)


def test_worker_falls_back_to_next_ranked_mode_when_download_fails(
    download_manager, sample_item, mock_callback
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        },
        download_errors={"public": DownloadError("HTTP Error 403: Forbidden")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["browser"]
    assert sample_item.resolution == "1080p"
    assert "Download via signed out failed - trying signed in via firefox" in _logged(
        mock_callback
    )


def test_worker_raises_when_every_download_attempt_fails(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        },
        download_errors={
            "browser": DownloadError("fragment 3 missing"),
            "public": DownloadError("HTTP Error 403: Forbidden"),
        },
    )
    with pytest.raises(Exception, match="yt-dlp error") as err:
        _work(download_manager, sample_item, sessions)
    assert "signed out: HTTP Error 403" in str(err.value)
    assert "signed in via firefox: fragment 3 missing" in str(err.value)


def test_worker_logs_when_modes_disagree_on_resolution(
    download_manager, sample_item, mock_callback
):
    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        }
    )
    _work(download_manager, sample_item, sessions)
    assert (
        "Quality check: signed in via firefox offers 1080p; signed out offers 4K "
        "- using signed out"
    ) in _logged(mock_callback)


def test_worker_warns_when_file_on_disk_is_below_selection(
    download_manager, sample_item, mock_callback
):
    sessions = _fake_sessions(infos={"public": select(_BEST, HLS_ONLY_1080)})
    with patch.object(DownloadManager, "_output_video_height", return_value=720):
        _work(download_manager, sample_item, sessions)
    assert (
        "Quality warning: Test Video was delivered at 720p but 1080p was selected"
        in _logged(mock_callback)
    )


@pytest.mark.parametrize("on_disk", [1080, 0])  # matches, or couldn't be read
def test_worker_does_not_warn_unless_file_is_below_selection(
    download_manager, sample_item, mock_callback, on_disk
):
    sessions = _fake_sessions(infos={"public": select(_BEST, HLS_ONLY_1080)})
    with patch.object(DownloadManager, "_output_video_height", return_value=on_disk):
        _work(download_manager, sample_item, sessions)
    assert not [m for m in _logged(mock_callback) if m.startswith("Quality warning")]


def test_worker_skips_delivered_check_in_audio_only_mode(download_manager, sample_item):
    download_manager.config.download.audio_only = True
    sessions = _fake_sessions(infos={"public": select(_BEST, HLS_ONLY_1080)})
    with patch.object(DownloadManager, "_output_video_height") as probe:
        _work(download_manager, sample_item, sessions)
    probe.assert_not_called()


def test_worker_audio_only_ranks_modes_by_audio_bitrate(download_manager, sample_item):
    download_manager.config.download.audio_only = True
    download_manager.config.download.cookies_from_browser = "firefox"
    spec = "bestaudio/best"
    sessions = _fake_sessions(
        infos={
            "browser": select(
                spec, [fmt("140", "m4a", None, "none", "mp4a.40.2", tbr=129)]
            ),
            "public": select(spec, [fmt("251", "webm", None, "none", "opus", tbr=160)]),
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]
    assert record["opts"]["public"]["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_worker_closes_every_probe_session_on_success(download_manager, sample_item):
    download_manager.config.download.cookies_from_browser = "firefox"
    download_manager.config.download.cookies_file = "/tmp/cookies.txt"
    sessions = _fake_sessions(
        infos={
            mode: select(_BEST, ADAPTIVE_4K) for mode in ("browser", "public", "file")
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert sorted(record["closed"]) == ["browser", "file", "public"]


def test_worker_closes_every_probe_session_on_failure(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={"browser": select(_BEST, ADAPTIVE_4K)},
        extract_errors={"public": DownloadError("boom")},
        download_errors={"browser": DownloadError("boom")},
    )
    with pytest.raises(Exception, match="yt-dlp error"):
        _work(download_manager, sample_item, sessions)
    assert sorted(sessions.record["closed"]) == ["browser", "public"]


def test_worker_never_passes_dead_user_agent_option(download_manager, sample_item):
    download_manager.config.download.cookies_from_browser = "firefox"
    download_manager.config.download.cookies_file = "/tmp/cookies.txt"
    record = _work(download_manager, sample_item, _fake_sessions())
    assert set(record["opts"]) == {"browser", "public", "file"}
    assert all("user_agent" not in opts for opts in record["opts"].values())


def test_worker_probes_without_resolving_playlist_entries(
    download_manager, sample_item
):
    download_manager.config.download.cookies_from_browser = "firefox"
    record = _work(download_manager, sample_item, _fake_sessions())
    assert [o["extract_flat"] for o in record["all_opts"]] == ["in_playlist"] * 2


def test_worker_downloads_playlist_lazily_through_best_mode(
    download_manager, sample_item
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    playlist = {"_type": "playlist", "title": "Mix", "entries": []}
    sessions = _fake_sessions(
        infos={"browser": playlist, "public": playlist},
        download_errors={"browser": DownloadError("entry 3 failed")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == []  # never via the probe's info dict
    [(mode, urls, opts)] = record["url_downloads"]
    assert (mode, urls) == ("public", [sample_item.url])
    assert "extract_flat" not in opts


def test_worker_audio_only_prefers_audio_stream_over_combined_video_fallback(
    download_manager, sample_item
):
    # Signed-in HLS has no audio-only formats, so its /best fallback is 1080p
    # video; that must not beat a real audio stream.
    download_manager.config.download.audio_only = True
    download_manager.config.download.cookies_from_browser = "firefox"
    spec = "bestaudio/best"
    sessions = _fake_sessions(
        infos={
            "browser": select(spec, HLS_ONLY_1080),
            "public": select(spec, [fmt("251", "webm", None, "none", "opus", tbr=135)]),
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]


def test_worker_prefers_mode_that_sees_the_playlist_over_single_video(
    download_manager, sample_item
):
    # e.g. watch?v=X&list=WL: signed out can't see the private list and falls
    # back to the single video.
    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": {"_type": "playlist", "title": "Watch later", "entries": []},
            "public": select(_BEST, ADAPTIVE_4K),
        }
    )
    record = _work(download_manager, sample_item, sessions)
    assert [m for m, _, _ in record["url_downloads"]] == ["browser"]
    assert record["downloaded"] == []


def test_worker_treats_empty_extraction_as_mode_failure(download_manager, sample_item):
    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={"browser": None, "public": select(_BEST, ADAPTIVE_4K)}
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]

    download_manager.config.download.cookies_from_browser = None
    with pytest.raises(Exception, match="returned no video information"):
        _work(download_manager, sample_item, _fake_sessions(infos={"public": None}))


def test_worker_fallback_extracts_again_for_fresh_urls(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        },
        download_errors={"public": DownloadError("HTTP Error 403: Forbidden")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["extract_calls"][-1] == ("browser", True)


def test_worker_resets_attempt_state_before_fallback(download_manager, sample_item):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"
    sessions = _fake_sessions(
        infos={
            "browser": {"title": "Test Video"},  # no height: leaves resolution unset
            "public": select(_BEST, ADAPTIVE_4K),
        },
        download_errors={"public": DownloadError("HTTP Error 403: Forbidden")},
    )
    sample_item.already_exists = True
    sample_item.resolution = "4K"
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["browser"]
    assert sample_item.already_exists is False
    assert sample_item.resolution == ""


def test_worker_close_error_does_not_fail_finished_download(
    download_manager, sample_item, mock_callback
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_file = "/tmp/cookies.txt"
    sessions = _fake_sessions(
        infos={"public": select(_BEST, ADAPTIVE_4K)},
        close_errors={"file": DownloadError("cookies.txt is not a Netscape file")},
    )
    record = _work(download_manager, sample_item, sessions)
    assert record["downloaded"] == ["public"]
    assert sorted(record["closed"]) == ["file", "public"]
    assert any(
        m.startswith("Could not close a yt-dlp session cleanly")
        for m in _logged(mock_callback)
    )


def test_worker_cancelled_before_probing_contacts_nothing(
    download_manager, sample_item
):
    sample_item.status = DownloadStatus.CANCELLED
    record = _work(download_manager, sample_item, _fake_sessions())
    assert record["all_opts"] == []


def test_worker_stopped_during_probing_downloads_nothing(download_manager, sample_item):
    sessions = _fake_sessions(infos={"public": select(_BEST, ADAPTIVE_4K)})

    def stop_then_probe(opts):
        session = sessions(opts)
        download_manager._stop_event.set()
        return session

    stop_then_probe.record = sessions.record
    record = _work(download_manager, sample_item, stop_then_probe)
    assert record["extract_calls"] == [("public", False)]
    assert record["downloaded"] == []


def test_worker_cancelled_between_attempts_stops_falling_back(
    download_manager, sample_item
):
    from yt_dlp.utils import DownloadError

    download_manager.config.download.cookies_from_browser = "firefox"

    class CancelOnFailure(DownloadError):
        def __init__(self, msg):
            super().__init__(msg)
            sample_item.status = DownloadStatus.CANCELLED

    sessions = _fake_sessions(
        infos={
            "browser": select(_BEST, HLS_ONLY_1080),
            "public": select(_BEST, ADAPTIVE_4K),
        },
    )
    sessions_record = sessions.record

    def factory(opts):
        session = sessions(opts)
        if _mode_of(opts) == "public":

            def fail(info, download=True):
                raise CancelOnFailure("cancelled mid-download")

            session.process_ie_result = fail
        return session

    factory.record = sessions_record
    record = _work(download_manager, sample_item, factory)
    assert record["downloaded"] == []


def test_probe_logger_names_mode_only_when_several_modes(download_manager, sample_item):
    from flowsnip.download_manager import _ModeLogger

    record = _work(download_manager, sample_item, _fake_sessions())
    assert not isinstance(record["opts"]["public"]["logger"], _ModeLogger)

    download_manager.config.download.cookies_from_browser = "firefox"
    record = _work(download_manager, sample_item, _fake_sessions())
    assert isinstance(record["opts"]["public"]["logger"], _ModeLogger)


def test_mode_logger_prefixes_errors_and_passes_other_levels_through():
    from flowsnip.download_manager import _ModeLogger

    inner = MagicMock()
    logger = _ModeLogger(inner, "signed out")
    logger.error("ERROR: [youtube] x: Sign in to confirm your age")
    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    inner.error.assert_called_once_with(
        "[signed out] [youtube] x: Sign in to confirm your age"
    )
    inner.debug.assert_called_once_with("d")
    inner.info.assert_called_once_with("i")
    inner.warning.assert_called_once_with("w")


def test_reprocessing_probe_info_downloads_exactly_the_probed_formats():
    # Guards the yt-dlp API assumption behind reusing a probe: running a
    # download=False result through process_ie_result(download=True) must pick
    # the same formats rather than re-selecting differently.
    from yt_dlp import YoutubeDL

    downloaded = []

    class RecordingYoutubeDL(YoutubeDL):
        def process_info(self, info_dict):
            downloaded.append(info_dict["format_id"])

    for formats, expected in ((ADAPTIVE_4K, "401+251"), (HLS_ONLY_1080, "96")):
        probed = select(_BEST, formats)
        downloaded.clear()
        with RecordingYoutubeDL({"format": _BEST, "quiet": True}) as ydl:
            ydl.process_ie_result(probed, download=True)
        assert downloaded == [expected]


def test_worker_no_callback_survives_cookie_db_error_and_fallback(
    test_config, sample_item
):
    from yt_dlp.utils import DownloadError

    test_config.download.cookies_from_browser = "chrome"
    mgr = DownloadManager(test_config)  # no callback
    sessions = _fake_sessions(
        infos={
            "public": select(_BEST, ADAPTIVE_4K),
            "browser": select(_BEST, HLS_ONLY_1080),
        },
        extract_errors={"browser": Exception("database is locked")},
        download_errors={"public": DownloadError("403")},
    )
    with pytest.raises(Exception, match="yt-dlp error"):
        _work(mgr, sample_item, sessions)
    mgr.stop_downloads()


# ---------------------------------------------------------------------------
# _output_video_height (ffprobe on the finished file)
# ---------------------------------------------------------------------------


def _downloads(*paths):
    return {"requested_downloads": [{"filepath": str(p)} for p in paths]}


def test_output_video_height_is_unknown_without_a_finished_file(tmp_path):
    assert DownloadManager._output_video_height(MagicMock(), None) == 0
    missing = _downloads(tmp_path / "missing.webm")
    assert DownloadManager._output_video_height(MagicMock(), missing) == 0


def test_output_video_height_reads_video_streams_and_skips_cover_art(tmp_path):
    path = tmp_path / "video.mkv"
    path.write_text("")
    metadata = {
        "streams": [
            {
                "codec_type": "video",
                "width": 3840,
                "height": 2160,
                "disposition": {"attached_pic": 1},
            },
            {"codec_type": "video", "width": 1920, "height": 1012},
            {"codec_type": "audio"},
        ]
    }
    with patch("yt_dlp.postprocessor.FFmpegPostProcessor") as ffprobe:
        ffprobe.return_value.probe_available = True
        ffprobe.return_value.get_metadata_object.return_value = metadata
        height = DownloadManager._output_video_height(MagicMock(), _downloads(path))
    assert height == 1080


def test_output_video_height_is_unknown_when_ffprobe_is_missing_or_fails(tmp_path):
    path = tmp_path / "video.mkv"
    path.write_text("")
    with patch("yt_dlp.postprocessor.FFmpegPostProcessor") as ffprobe:
        ffprobe.return_value.probe_available = False
        assert DownloadManager._output_video_height(MagicMock(), _downloads(path)) == 0
    with patch("yt_dlp.postprocessor.FFmpegPostProcessor") as ffprobe:
        ffprobe.return_value.probe_available = True
        ffprobe.return_value.get_metadata_object.side_effect = Exception("bad file")
        assert DownloadManager._output_video_height(MagicMock(), _downloads(path)) == 0


@pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg"
)
def test_output_video_height_probes_a_real_file(tmp_path):
    from yt_dlp import YoutubeDL

    path = tmp_path / "clip.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1920x1012:d=0.2",
            "-c:v",
            "ffv1",
            str(path),
        ],
        check=True,
    )
    with YoutubeDL({"quiet": True}) as ydl:
        assert DownloadManager._output_video_height(ydl, _downloads(path)) == 1080


# ---------------------------------------------------------------------------
# bundled ffmpeg (frozen builds)
# ---------------------------------------------------------------------------


def _base_opts(manager, item):
    return manager._build_base_opts(
        item, manager._make_progress_hook(item), manager._make_ydl_logger(item)
    )


def test_frozen_build_points_ytdlp_at_bundled_ffmpeg(
    download_manager, sample_item, tmp_path, monkeypatch
):
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert _base_opts(download_manager, sample_item)["ffmpeg_location"] == str(tmp_path)


def test_frozen_build_falls_back_to_executable_dir_for_ffmpeg(
    download_manager, sample_item, tmp_path, monkeypatch
):
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    (exe_dir / "ffmpeg.exe").write_text("")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path / "internal"), raising=False)
    monkeypatch.setattr("sys.executable", str(exe_dir / "FlowSnip.exe"))
    assert _base_opts(download_manager, sample_item)["ffmpeg_location"] == str(exe_dir)


def test_frozen_build_without_bundled_ffmpeg_leaves_location_unset(
    download_manager, sample_item, tmp_path, monkeypatch
):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr("sys.executable", str(tmp_path / "FlowSnip"))
    assert "ffmpeg_location" not in _base_opts(download_manager, sample_item)


def test_build_base_opts_without_js_runtime_omits_js_runtimes(
    download_manager, sample_item
):
    with patch("flowsnip.download_manager._get_js_runtime", return_value=None):
        opts = _base_opts(download_manager, sample_item)
    assert "js_runtimes" not in opts


def test_source_run_leaves_ffmpeg_location_unset(download_manager, sample_item):
    assert "ffmpeg_location" not in _base_opts(download_manager, sample_item)


# ---------------------------------------------------------------------------
# _download_worker - audio-only and ytdl option flags
# ---------------------------------------------------------------------------


def test_worker_audio_only(download_manager, sample_item):
    download_manager.config.download.audio_only = True
    factory = _make_ytdl()
    opts = _run_worker(download_manager, sample_item, factory)
    assert "postprocessors" in opts
    assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    download_manager.config.download.audio_only = False


def test_worker_ytdl_flags(download_manager, sample_item):
    download_manager.config.ytdl.write_info_json = True
    download_manager.config.ytdl.write_description = True
    download_manager.config.ytdl.embed_subs = True
    download_manager.config.ytdl.add_metadata = True
    factory = _make_ytdl()
    opts = _run_worker(download_manager, sample_item, factory)
    assert opts.get("writeinfojson") is True
    assert opts.get("writedescription") is True
    assert opts.get("writesubtitles") is True
    assert opts.get("addmetadata") is True
    # reset
    download_manager.config.ytdl.write_info_json = False
    download_manager.config.ytdl.write_description = False
    download_manager.config.ytdl.embed_subs = False


def test_worker_ytdl_flags_embed_subs_disabled(download_manager, sample_item):
    download_manager.config.ytdl.embed_subs = False
    factory = _make_ytdl()
    opts = _run_worker(download_manager, sample_item, factory)
    assert "writesubtitles" not in opts
    assert "writeautomaticsub" not in opts


# ---------------------------------------------------------------------------
# _download_worker - logger inner function branches
# ---------------------------------------------------------------------------


def _get_logger(download_manager, sample_item):
    """Run worker and return the captured logger object."""
    factory = _make_ytdl()
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        download_manager._download_worker(sample_item)
    return factory.captured["opts"]["logger"]


def test_logger_none_msg(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug(None)  # if msg: is False - should not crash


def test_logger_empty_msg(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("")


def test_logger_mib_conversion_with_number(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Downloading at 5.5 MiB/s")


def test_logger_mib_conversion_no_number(download_manager, sample_item):
    # "MiB/s" present but no numeric prefix - speed_match is None
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Speed in MiB/s units")


def test_logger_kib_conversion_with_number(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Downloading at 500.0 KiB/s")


def test_logger_kib_conversion_no_number(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Rate in KiB/s units")


def test_logger_download_progress_at_5pct(download_manager, sample_item, mock_callback):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("[download]   5.0% of 100MB")
    mock_callback.assert_any_call(
        "log_message", {"message": "[download]   5.0% of 100MB"}
    )


def test_logger_download_progress_non_5pct(
    download_manager, sample_item, mock_callback
):
    logger = _get_logger(download_manager, sample_item)
    mock_callback.reset_mock()
    logger.debug("[download]   3.0% of 100MB")
    # 3% is not divisible by 5 - should NOT log a progress message
    progress_calls = [
        c
        for c in mock_callback.call_args_list
        if c[0][0] == "log_message" and "3.0%" in str(c)
    ]
    assert progress_calls == []


def test_logger_download_progress_100pct_duplicate_suppressed(
    download_manager, sample_item, mock_callback
):
    logger = _get_logger(download_manager, sample_item)
    mock_callback.reset_mock()
    logger.debug("[download] 100% of 100MB")
    logger.debug("[download] 100% of 100MB")
    # Second identical percent call should be suppressed
    calls_100 = [c for c in mock_callback.call_args_list if "100%" in str(c)]
    assert len(calls_100) == 1


def test_logger_download_unparseable_percent(
    download_manager, sample_item, mock_callback
):
    logger = _get_logger(download_manager, sample_item)
    mock_callback.reset_mock()
    # int(float("??")) raises ValueError - hits the except branch
    logger.debug("[download] ??% of 100MB")
    mock_callback.assert_any_call("log_message", {"message": "[download] ??% of 100MB"})


def test_logger_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config, None)
    factory = _make_ytdl()
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        mgr._download_worker(sample_item)
    logger = factory.captured["opts"]["logger"]
    logger.debug("[download]   5.0% of 100MB")  # progress_callback is None - no crash
    logger.debug("Some other message")
    mgr.stop_downloads()


def test_logger_mib_speed_with_space(download_manager, sample_item, mock_callback):
    # Tests the second replace (with space) is also exercised
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Speed: 2.5 MiB/s now")


def test_logger_kib_speed_with_space(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    logger.debug("Speed: 128.0 KiB/s now")


def test_logger_already_downloaded_sets_flag(download_manager, sample_item):
    logger = _get_logger(download_manager, sample_item)
    assert sample_item.already_exists is False
    logger.debug("[download] test.mp4 has already been downloaded")
    assert sample_item.already_exists is True


# ---------------------------------------------------------------------------
# _download_worker - progress_hook inner function branches
# ---------------------------------------------------------------------------


def _capture_hooks(download_manager, sample_item):
    factory = _make_ytdl()
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        download_manager._download_worker(sample_item)
    return factory.captured["opts"].get("progress_hooks", [])


def test_progress_hook_fragment_based(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": 3,
                "fragment_count": 10,
                "_speed_str": "5.0 MiB/s",
                "downloaded_bytes": 3000,
                "total_bytes": 10000,
            }
        )
    assert sample_item.progress == pytest.approx(30.0)


def test_progress_hook_percentage_based(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": " 50.0%",
                "_speed_str": "500 KiB/s",
                "downloaded_bytes": 5000,
                "total_bytes": 0,
                "total_bytes_estimate": 10000,
            }
        )
    assert sample_item.progress == pytest.approx(50.0)


def test_progress_hook_percentage_invalid_falls_to_zero(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "N/A%",
                "_speed_str": "",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    assert sample_item.progress == 0.0


def test_progress_hook_mib_speed_conversion(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "10%",
                "_speed_str": "2.0 MiB/s",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    assert "Mbps" in sample_item.speed


def test_progress_hook_mib_speed_invalid(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "10%",
                "_speed_str": "N/A MiB/s",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    assert "MiB" not in sample_item.speed or "Mbps" in sample_item.speed


def test_progress_hook_kib_speed_conversion(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "10%",
                "_speed_str": "200.0 KiB/s",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    assert "Mbps" in sample_item.speed


def test_progress_hook_kib_speed_invalid(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "10%",
                "_speed_str": "N/A KiB/s",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )


def test_progress_hook_other_speed(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": None,
                "fragment_count": None,
                "_percent_str": "10%",
                "_speed_str": "100 B/s",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    assert sample_item.speed == "100 B/s"


def test_progress_hook_finished(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook({"status": "finished", "filename": "/tmp/test.mp4"})
    assert sample_item.progress == 100.0
    assert sample_item.output_path == Path("/tmp/test.mp4")


def test_progress_hook_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config, None)
    factory = _make_ytdl()
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        mgr._download_worker(sample_item)
    hooks = factory.captured["opts"].get("progress_hooks", [])
    for hook in hooks:
        hook(
            {
                "status": "downloading",
                "fragment_index": 1,
                "fragment_count": 5,
                "_speed_str": "",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
        hook({"status": "finished", "filename": "/tmp/x.mp4"})
    mgr.stop_downloads()


def test_progress_hook_milestone_no_callback(test_config, sample_item):
    """Milestone branch with no callback must not crash."""
    mgr = DownloadManager(test_config, None)
    factory = _make_ytdl()
    with patch("yt_dlp.YoutubeDL", side_effect=factory):
        mgr._download_worker(sample_item)
    hooks = factory.captured["opts"].get("progress_hooks", [])
    for hook in hooks:
        # 50% progress hits the 25% milestone; callback is None
        hook(
            {
                "status": "downloading",
                "fragment_index": 2,
                "fragment_count": 4,
                "_speed_str": "",
                "downloaded_bytes": 0,
                "total_bytes": 0,
            }
        )
    mgr.stop_downloads()


# ---------------------------------------------------------------------------
# Queue manager integration (start → process → complete/fail)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_queue_manager_completes_download(test_config, mock_callback):
    """Item queued after start_downloads ends up in completed_downloads."""
    test_config.download.retry_attempts = 1
    done = threading.Event()

    def on_callback(event_type, data):
        if event_type in ("download_completed", "download_failed"):
            done.set()

    def fast_worker(item):
        pass  # instant success

    with patch.object(DownloadManager, "_download_worker", fast_worker):
        mgr = DownloadManager(test_config, on_callback)
        mgr.start_downloads()
        item = DownloadItem(url="https://youtube.com/watch?v=test", title="T")
        mgr.pending_queue.put(item)
        assert done.wait(timeout=5.0), "Download did not complete within 5 s"
        mgr.stop_downloads()

    assert len(mgr.completed_downloads) + len(mgr.failed_downloads) >= 1


@pytest.mark.slow
def test_queue_manager_retries_then_fails(test_config, mock_callback):
    """Item that always raises eventually lands in failed_downloads."""
    test_config.download.retry_attempts = 1
    done = threading.Event()

    def on_callback(event_type, data):
        if event_type == "download_failed":
            done.set()

    def failing_worker(item):
        raise Exception("download broke")

    mgr = DownloadManager(test_config, on_callback)
    with patch.object(mgr, "_download_worker", side_effect=failing_worker):
        mgr.start_downloads()
        item = DownloadItem(url="https://youtube.com/watch?v=test", title="T")
        mgr.pending_queue.put(item)
        assert done.wait(timeout=5.0), "Download did not fail within 5 s"
        mgr.stop_downloads()

    assert len(mgr.failed_downloads) == 1
    assert mgr.failed_downloads[0].status == DownloadStatus.FAILED


@pytest.mark.slow
def test_queue_manager_paused_does_not_consume(download_manager):
    started = threading.Event()
    original_start = download_manager._start_download

    def spy(item):
        started.set()
        original_start(item)

    download_manager._start_download = spy
    download_manager.start_downloads()
    download_manager.pause_downloads()
    item = DownloadItem(url="https://youtube.com/watch?v=test", title="T")
    download_manager.pending_queue.put(item)
    # Wait longer than one queue cycle (500 ms); started must not fire
    assert not started.wait(timeout=0.8), "Item was consumed despite being paused"
    assert download_manager.pending_queue.qsize() == 1


# ---------------------------------------------------------------------------
# __del__
# ---------------------------------------------------------------------------


def test_del_while_running(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    mgr.start_downloads()
    mgr.__del__()
    assert mgr._force_shutdown is True


def test_del_while_not_running(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    mgr.__del__()  # should not raise


# ---------------------------------------------------------------------------
# _get_yt_dlp lazy accessor
# ---------------------------------------------------------------------------


def test_get_yt_dlp_imports_on_first_call():
    import flowsnip.download_manager as dm

    original = dm._yt_dlp_module
    try:
        dm._yt_dlp_module = None
        result = _get_yt_dlp()
        import yt_dlp

        assert result is yt_dlp
    finally:
        dm._yt_dlp_module = original


def test_get_yt_dlp_returns_cached():
    import flowsnip.download_manager as dm

    original = dm._yt_dlp_module
    try:
        dm._yt_dlp_module = None
        r1 = _get_yt_dlp()
        r2 = _get_yt_dlp()
        assert r1 is r2
    finally:
        dm._yt_dlp_module = original


# ---------------------------------------------------------------------------
# _get_js_runtime lazy accessor
# ---------------------------------------------------------------------------


def test_get_js_runtime_calls_find_on_first_call():
    import flowsnip.download_manager as dm

    original = dm._JS_RUNTIME
    try:
        dm._JS_RUNTIME = _UNSET
        fake = {"node": {"path": "/usr/bin/node"}}
        with patch("flowsnip.download_manager._find_js_runtime", return_value=fake):
            result = _get_js_runtime()
        assert result == fake
    finally:
        dm._JS_RUNTIME = original


def test_get_js_runtime_returns_cached():
    import flowsnip.download_manager as dm

    original = dm._JS_RUNTIME
    try:
        dm._JS_RUNTIME = {"cached": True}
        result = _get_js_runtime()
        assert result == {"cached": True}
    finally:
        dm._JS_RUNTIME = original


# ---------------------------------------------------------------------------
# MAX_HISTORY trimming
# ---------------------------------------------------------------------------


def test_cancel_download_trims_completed_history(download_manager):
    for i in range(MAX_HISTORY):
        download_manager.completed_downloads.append(
            DownloadItem(url=f"https://y.com/v={i}", title=f"V{i}")
        )
    extra = DownloadItem(url="https://y.com/v=x", title="X")
    future = MagicMock()
    download_manager.active_downloads[extra.id] = extra
    download_manager.download_tasks[extra.id] = future
    download_manager.cancel_download(extra.id)
    assert len(download_manager.completed_downloads) == MAX_HISTORY


def test_process_completed_trims_completed_history(download_manager):
    for i in range(MAX_HISTORY):
        download_manager.completed_downloads.append(
            DownloadItem(url=f"https://y.com/v={i}", title=f"V{i}")
        )
    item = DownloadItem(url="https://y.com/v=x", title="X")
    future = MagicMock()
    future.done.return_value = True
    future.result.return_value = None
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future
    download_manager._process_completed_tasks()
    assert len(download_manager.completed_downloads) == MAX_HISTORY


# ---------------------------------------------------------------------------
# _height_to_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "height, expected",
    [
        (4320, "8K"),
        (2160, "4K"),
        (1440, "1440p"),
        (1080, "1080p"),
        (720, "720p"),
        (480, "480p"),
        (360, "360p"),
        (240, "240p"),
        (144, "144p"),
    ],
)
def test_height_to_label(height, expected):
    assert _height_to_label(height) == expected


@pytest.mark.parametrize(
    "width, height, expected",
    [
        (1920, 1012, "1080p"),  # cinemascope crop of a 1080p frame
        (3840, 1600, "4K"),
        (1080, 1920, "1080p"),  # portrait
        (7680, 4320, "8K"),
        (1440, 1080, "1080p"),  # 4:3
        (1280, 720, "720p"),
    ],
)
def test_height_to_label_uses_frame_size(width, height, expected):
    assert _height_to_label(height, width) == expected


# ---------------------------------------------------------------------------
# progress hook - resolution capture
# ---------------------------------------------------------------------------


def test_progress_hook_finished_sets_resolution(download_manager, sample_item):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook(
            {
                "status": "finished",
                "filename": "/tmp/test.mp4",
                "info_dict": {"height": 1080},
            }
        )
    assert sample_item.resolution == "1080p"


def test_progress_hook_finished_labels_by_frame_size(download_manager, sample_item):
    hook = download_manager._make_progress_hook(sample_item)
    hook(
        {
            "status": "finished",
            "filename": "/tmp/test.mkv",
            "info_dict": {"height": 1012, "width": 1920},
        }
    )
    assert sample_item.resolution == "1080p"


def test_progress_hook_finished_no_height_leaves_resolution_empty(
    download_manager, sample_item
):
    hooks = _capture_hooks(download_manager, sample_item)
    for hook in hooks:
        hook({"status": "finished", "filename": "/tmp/test.mp4"})
    assert sample_item.resolution == ""


# ---------------------------------------------------------------------------
# completion log message includes resolution
# ---------------------------------------------------------------------------


def test_process_completed_log_includes_resolution(download_manager, mock_callback):
    item = DownloadItem(url="https://y.com/v=x", title="My Video")
    item.resolution = "1080p"
    future = MagicMock()
    future.done.return_value = True
    future.result.return_value = None
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future
    download_manager._process_completed_tasks()
    mock_callback.assert_any_call(
        "log_message", {"message": "Download completed: My Video [1080p]"}
    )


def test_process_completed_log_no_resolution(download_manager, mock_callback):
    item = DownloadItem(url="https://y.com/v=x", title="My Video")
    future = MagicMock()
    future.done.return_value = True
    future.result.return_value = None
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future
    download_manager._process_completed_tasks()
    mock_callback.assert_any_call(
        "log_message", {"message": "Download completed: My Video"}
    )


def test_process_completed_trims_failed_history(download_manager):
    download_manager.config.download.retry_attempts = 0
    for i in range(MAX_HISTORY):
        fi = DownloadItem(url=f"https://y.com/v={i}", title=f"V{i}")
        fi.retry_count = 1
        download_manager.failed_downloads.append(fi)
    item = DownloadItem(url="https://y.com/v=x", title="X")
    item.retry_count = 1  # already exceeds retry_attempts=0
    future = MagicMock()
    future.done.return_value = True
    future.result.side_effect = Exception("fail")
    download_manager.active_downloads[item.id] = item
    download_manager.download_tasks[item.id] = future
    download_manager._process_completed_tasks()
    assert len(download_manager.failed_downloads) == MAX_HISTORY


# ---------------------------------------------------------------------------
# Branch coverage - no-callback paths and edge cases
# ---------------------------------------------------------------------------


def test_extract_title_browser_cookies_no_js_runtime(download_manager):
    download_manager.config.download.cookies_from_browser = "chrome"
    with patch("flowsnip.download_manager._get_js_runtime", return_value=None):
        factory = _make_ytdl(title="Video")
        with patch("yt_dlp.YoutubeDL", side_effect=factory):
            result = download_manager._extract_title("https://youtube.com/watch?v=test")
    assert result == "Video"
    assert "js_runtimes" not in factory.captured.get("opts", {})
    download_manager.config.download.cookies_from_browser = None


def test_add_download_invalid_url_no_callback(test_config):
    mgr = DownloadManager(test_config)
    result = mgr.add_download("not-a-url")
    assert result == ""
    mgr.stop_downloads()


def test_add_download_error_title_no_callback(test_config):
    mgr = DownloadManager(test_config)
    with patch.object(mgr, "_extract_title", return_value="__error__:some error"):
        result = mgr.add_download("https://example.com/video")
    assert result != ""
    mgr.stop_downloads()


def test_pause_downloads_no_callback(test_config):
    mgr = DownloadManager(test_config)
    mgr.start_downloads()
    mgr.pause_downloads()
    assert mgr.is_paused
    mgr.stop_downloads()


def test_resume_downloads_no_callback(test_config):
    mgr = DownloadManager(test_config)
    mgr.is_paused = True
    mgr.resume_downloads()
    assert not mgr.is_paused
    mgr.stop_downloads()


def test_stop_downloads_active_without_task(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    item = DownloadItem(url="https://example.com", title="Test")
    mgr.active_downloads[item.id] = item  # active but NOT in download_tasks
    mgr.stop_downloads()
    assert len(mgr.active_downloads) == 0


def test_cancel_download_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config)
    mgr.active_downloads[sample_item.id] = sample_item
    mgr.cancel_download(sample_item.id)
    assert sample_item.id not in mgr.active_downloads
    mgr.stop_downloads()


def test_retry_download_iterates_past_non_matching_no_callback(test_config):
    mgr = DownloadManager(test_config)
    other = DownloadItem(url="https://example.com/other", title="Other")
    item = DownloadItem(url="https://example.com/video", title="Target")
    item.status = DownloadStatus.FAILED
    mgr.failed_downloads = [
        other,
        item,
    ]  # item is second - forces loop to iterate past other
    mgr.retry_download(item.id)
    assert item not in mgr.failed_downloads
    assert mgr.pending_queue.qsize() == 1
    mgr.stop_downloads()


def test_remove_download_unknown_queue(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    mgr.remove_download("some-id", from_queue="unknown")
    mock_callback.assert_called_with(
        "download_removed", {"id": "some-id", "queue": "unknown"}
    )
    mgr.stop_downloads()


def test_remove_download_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config)
    mgr.failed_downloads = [sample_item]
    mgr.remove_download(sample_item.id)
    assert sample_item not in mgr.failed_downloads
    mgr.stop_downloads()


def test_process_completed_task_not_in_active(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    future = MagicMock()
    future.done.return_value = True
    mgr.download_tasks["ghost-id"] = future  # task exists but NOT in active_downloads
    mgr._process_completed_tasks()
    assert "ghost-id" not in mgr.download_tasks
    mgr.stop_downloads()


def test_process_completed_success_no_callback(test_config):
    mgr = DownloadManager(test_config)
    item = DownloadItem(url="https://y.com/v=x", title="T")
    future = MagicMock()
    future.done.return_value = True
    future.result.return_value = None
    mgr.active_downloads[item.id] = item
    mgr.download_tasks[item.id] = future
    mgr._process_completed_tasks()
    assert item.status == DownloadStatus.COMPLETED
    mgr.stop_downloads()


def test_process_completed_retry_no_callback(test_config):
    mgr = DownloadManager(test_config)  # retry_attempts=1 from fixture
    item = DownloadItem(url="https://y.com/v=x", title="T")
    future = MagicMock()
    future.done.return_value = True
    future.result.side_effect = Exception("fail")
    mgr.active_downloads[item.id] = item
    mgr.download_tasks[item.id] = future
    mgr._process_completed_tasks()
    assert item.retry_count == 1
    assert mgr.pending_queue.qsize() == 1
    mgr.stop_downloads()


def test_process_completed_failed_no_callback(test_config):
    test_config.download.retry_attempts = 0
    mgr = DownloadManager(test_config)
    item = DownloadItem(url="https://y.com/v=x", title="T")
    item.retry_count = 1  # exceeds retry_attempts=0
    future = MagicMock()
    future.done.return_value = True
    future.result.side_effect = Exception("fail")
    mgr.active_downloads[item.id] = item
    mgr.download_tasks[item.id] = future
    mgr._process_completed_tasks()
    assert item.status == DownloadStatus.FAILED
    mgr.stop_downloads()


def test_start_download_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config)
    mgr._start_download(sample_item)
    assert sample_item.status == DownloadStatus.DOWNLOADING
    mgr.stop_downloads()


def test_ydl_logger_download_percent_parse_error_no_callback(test_config, sample_item):
    mgr = DownloadManager(test_config)  # no callback
    log_obj = mgr._make_ydl_logger(sample_item)
    log_obj.debug("[download] abc% of 10MB")  # "abc" can't be parsed as float


def test_queue_manager_exits_immediately_when_not_running(test_config, mock_callback):
    mgr = DownloadManager(test_config, mock_callback)
    # is_running is False by default - while condition fails immediately
    mgr._queue_manager()
    mgr.stop_downloads()


def test_progress_hook_unknown_status(download_manager, sample_item):
    hook = download_manager._make_progress_hook(sample_item)
    hook({"status": "error"})  # neither "downloading" nor "finished" - no-op


def test_build_base_opts_add_metadata_disabled(download_manager, sample_item):
    download_manager.config.ytdl.add_metadata = False
    progress_hook = download_manager._make_progress_hook(sample_item)
    log_obj = download_manager._make_ydl_logger(sample_item)
    opts = download_manager._build_base_opts(sample_item, progress_hook, log_obj)
    assert "addmetadata" not in opts
    download_manager.config.ytdl.add_metadata = True


def test_del_no_executor(test_config):
    mgr = DownloadManager(test_config)
    mgr.is_running = True
    saved_executor = mgr.executor
    del mgr.executor  # remove the attribute to trigger hasattr() False branch
    mgr.__del__()  # must not raise
    mgr.executor = saved_executor  # restore so cleanup doesn't fail
    mgr.is_running = False
    mgr.stop_downloads()
