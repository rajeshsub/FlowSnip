"""
Download manager for FlowSnip.

Handles parallel downloads, queue management, and error handling for yt-dlp operations.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from .config import Config


def _find_js_runtime() -> dict | None:
    """Find a JS runtime for yt-dlp's n-challenge solver.

    Returns a js_runtimes dict suitable for yt-dlp (e.g. {"node": {"path": "..."}}),
    or None if no supported runtime is found.

    Set FLOWSNIP_NODE_PATH=/path/to/node to override automatic detection.
    """
    # Explicit override via environment variable
    explicit = os.environ.get("FLOWSNIP_NODE_PATH")
    if explicit and os.path.isfile(explicit):
        return {"node": {"path": explicit}}

    # Prefer Node.js - check PATH first, then common Windows install locations.
    node = shutil.which("node") or shutil.which("nodejs")
    if node:
        return {"node": {"path": node}}

    for candidate in [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        os.path.expanduser(r"~\AppData\Roaming\nvm\current\node.exe"),
    ]:
        if os.path.exists(candidate):
            return {"node": {"path": candidate}}

    # Deno as a fallback
    deno = shutil.which("deno")
    if deno:
        return {"deno": {"path": deno}}

    return None


# Lazy accessors - avoid import-time cost of loading yt_dlp and probing the filesystem.
_UNSET = object()
_JS_RUNTIME = _UNSET  # populated on first download via _get_js_runtime()
_yt_dlp_module = None  # populated on first download via _get_yt_dlp()


def _get_yt_dlp() -> Any:
    """Return the yt_dlp module, importing it on the first call."""
    global _yt_dlp_module
    if _yt_dlp_module is None:
        import yt_dlp as _m

        _yt_dlp_module = _m
    return _yt_dlp_module


def _get_js_runtime() -> dict | None:
    """Return the JS runtime dict (or None), detecting it on the first call."""
    global _JS_RUNTIME
    if _JS_RUNTIME is _UNSET:
        _JS_RUNTIME = _find_js_runtime()
    return _JS_RUNTIME  # type: ignore[return-value]


def _bundled_ffmpeg_dir() -> str | None:
    """Directory holding the ffmpeg shipped inside a packaged build, if any.

    PyInstaller unpacks bundled data next to the app (sys._MEIPASS), which is
    not on PATH, so yt-dlp has to be told where ffmpeg is or every
    video+audio merge fails.
    """
    if not getattr(sys, "frozen", False):
        return None
    for directory in (getattr(sys, "_MEIPASS", None), os.path.dirname(sys.executable)):
        if directory and any(
            os.path.isfile(os.path.join(directory, name))
            for name in ("ffmpeg", "ffmpeg.exe")
        ):
            return directory
    return None


# Keywords that indicate a video requires authentication
_AUTH_KEYWORDS = frozenset(
    [
        "login required",
        "sign in",
        "sign-in",
        "private video",
        "members only",
        "age-restricted",
        "age restricted",
        "this video is private",
        "confirm your age",
        "requires payment",
        "join to watch",
        "not available",
        "unavailable",
    ]
)

MAX_HISTORY = 200  # max items kept in completed_downloads / failed_downloads

# Substrings of a browser-cookie extraction failure (browser running, DB locked).
_COOKIE_DB_ERRORS = ("could not copy", "database", "locked")


def _selected_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    """The formats yt-dlp chose in a processed info dict, in merge order."""
    return info.get("requested_formats") or [info]


def _video_rank(info: dict[str, Any]) -> tuple[int, float, float]:
    """Rank a video selection: resolution, then fps, then total bitrate."""
    selected = _selected_formats(info)
    height = max(
        _display_height(f.get("height") or 0, f.get("width")) for f in selected
    )
    fps = max(f.get("fps") or 0 for f in selected)
    bitrate = sum(f.get("tbr") or 0 for f in selected)
    return height, fps, bitrate


def _audio_rank(info: dict[str, Any]) -> tuple[int, float, float]:
    """Rank an audio-only selection: a pure audio stream first, then its bitrate.

    A mode without audio-only formats falls back to a combined video stream,
    whose resolution and bitrate say nothing about its audio.
    """
    selected = _selected_formats(info)
    pure_audio = all(f.get("vcodec") == "none" for f in selected)
    bitrate = max(f.get("abr") or f.get("tbr") or 0 for f in selected)
    return int(pure_audio), 0, bitrate


class _ModeLogger:
    """yt-dlp logger that names the access mode on errors.

    One mode failing is expected when another succeeds, so its error must not
    read as if the download failed.
    """

    def __init__(self, inner: Any, label: str) -> None:
        self._inner = inner
        self._label = label

    def debug(self, msg: str) -> None:
        self._inner.debug(msg)

    def info(self, msg: str) -> None:
        self._inner.info(msg)

    def warning(self, msg: str) -> None:
        self._inner.warning(msg)

    def error(self, msg: str) -> None:
        self._inner.error(f"[{self._label}] {msg.removeprefix('ERROR: ')}")


@dataclass
class _Candidate:
    """One access mode's extraction result, ready to download."""

    label: str
    mode_opts: dict[str, Any]
    session: Any
    info: dict[str, Any]
    rank: tuple[int, float, float]

    @property
    def is_playlist(self) -> bool:
        return self.info.get("_type") in ("playlist", "multi_video")


def _display_height(height: int, width: int | None = None) -> int:
    """Resolution class of a frame, independent of aspect ratio and orientation.

    A 1920x1012 cinemascope frame is 1080p and a 1080x1920 portrait frame is
    1080p: take the short side, or the 16:9 height implied by the long side if
    that is larger.
    """
    if not width:
        return height
    short_side, long_side = sorted((width, height))
    return max(short_side, round(long_side * 9 / 16))


def _height_to_label(height: int, width: int | None = None) -> str:
    """Convert a frame size to a human-readable resolution label."""
    height = _display_height(height, width)
    if height >= 4320:
        return "8K"
    if height >= 2160:
        return "4K"
    if height >= 1440:
        return "1440p"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    if height >= 480:
        return "480p"
    if height >= 360:
        return "360p"
    if height >= 240:
        return "240p"
    return f"{height}p"


class DownloadStatus(Enum):
    """Status of a download item."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class DownloadItem:
    """Represents a single download item."""

    id: str = field(default_factory=lambda: str(uuid4()))
    url: str = ""
    title: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    file_size: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error_message: str = ""
    retry_count: int = 0
    already_exists: bool = False
    resolution: str = ""
    output_path: Path | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None


class DownloadManager:
    """Manages download operations with queue and parallel processing."""

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Basic URL validation: only check for http(s) scheme, allow all domains."""
        import re

        return bool(re.match(r"^https?://", url))

    def _extract_title(self, url: str) -> str:
        """Extract video title. Returns '__error__:message' on failure."""
        # Attempt 1: browser cookies (includes PO token - best for YouTube)
        if self.config.download.cookies_from_browser:
            try:
                opts: dict[str, Any] = {
                    "quiet": True,
                    "cookiesfrombrowser": (
                        self.config.download.cookies_from_browser,
                        None,
                        None,
                        None,
                    ),
                }
                opts["remote_components"] = ["ejs:github"]
                if _get_js_runtime():
                    opts["js_runtimes"] = _get_js_runtime()
                with _get_yt_dlp().YoutubeDL(opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=False)
                    return info.get("title", "") or ""
            except Exception:
                pass

        # Attempt 2: default yt-dlp with optional cookie file (works for public videos)
        try:
            opts2: dict[str, Any] = {"quiet": True}
            opts2["remote_components"] = ["ejs:github"]
            if _get_js_runtime():
                opts2["js_runtimes"] = _get_js_runtime()
            if self.config.download.cookies_file:
                opts2["cookiefile"] = self.config.download.cookies_file
            with _get_yt_dlp().YoutubeDL(opts2) as ydl:  # type: ignore[arg-type]
                info = ydl.extract_info(url, download=False)
                return info.get("title", "") or ""
        except Exception as e:
            return f"__error__:Failed to fetch info: {e}"

    def __init__(
        self,
        config: Config,
        progress_callback: Callable[[str, Any], None] | None = None,
    ):
        """Initialize the download manager."""
        self.config = config
        self.progress_callback = progress_callback

        # Download queues
        self.pending_queue: Queue[DownloadItem] = Queue()
        self.active_downloads: dict[str, DownloadItem] = {}
        self.completed_downloads: list[DownloadItem] = []
        self.failed_downloads: list[DownloadItem] = []

        # Threading
        self.executor = ThreadPoolExecutor(
            max_workers=self.config.download.max_parallel_downloads
        )
        self.download_tasks: dict[str, Any] = {}

        # Control flags
        self.is_running = False
        self.is_paused = False
        self._stop_event = threading.Event()
        self._force_shutdown = False

        # Background thread for queue management
        self.queue_thread: threading.Thread | None = None

    def add_download(self, url: str) -> str:
        """Add a new download to the queue after validating the URL."""
        if not self.is_valid_url(url):
            if self.progress_callback:
                self.progress_callback(
                    "log_message", {"message": f"Invalid or unsupported URL: {url}"}
                )
            return ""
        title = self._extract_title(url)
        if title.startswith("__error__:"):
            if self.progress_callback:
                self.progress_callback("log_message", {"message": title[10:]})
            title = url.split("v=")[-1].split("&")[0] or "Unknown Video"

        download_item = DownloadItem(url=url, title=title)
        self.pending_queue.put(download_item)

        if self.progress_callback:
            self.progress_callback("download_added", download_item)

        return download_item.id

    def add_multiple_downloads(self, urls: list[str]) -> list[str]:
        """Add multiple downloads to the queue after validating URLs."""
        download_ids = []
        for url in urls:
            download_id = self.add_download(url)
            if download_id:
                download_ids.append(download_id)
        return download_ids

    def start_downloads(self) -> None:
        """Start the download manager."""
        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self._stop_event.clear()

        # Start the queue management thread
        self.queue_thread = threading.Thread(target=self._queue_manager, daemon=True)
        self.queue_thread.start()

    def pause_downloads(self) -> None:
        """Pause all downloads."""
        self.is_paused = True
        if self.progress_callback:
            self.progress_callback("downloads_paused", None)

    def resume_downloads(self) -> None:
        """Resume paused downloads."""
        self.is_paused = False
        if self.progress_callback:
            self.progress_callback("downloads_resumed", None)

    def stop_downloads(self) -> None:
        """Stop all downloads and cleanup."""
        self.is_running = False
        self._stop_event.set()
        self._force_shutdown = True

        # Cancel active downloads (non-blocking)
        for download_id in list(self.active_downloads.keys()):
            if download_id in self.download_tasks:
                future = self.download_tasks[download_id]
                future.cancel()

        # Clear all tasks and downloads immediately
        self.download_tasks.clear()
        self.active_downloads.clear()

        # Force shutdown executor immediately
        self.executor.shutdown(wait=False)

        # Create new executor for future use if needed
        self.executor = ThreadPoolExecutor(
            max_workers=self.config.download.max_parallel_downloads
        )

        if self.progress_callback:
            self.progress_callback("downloads_stopped", None)

    def cancel_download(self, download_id: str) -> None:
        """Cancel a specific download."""
        if download_id in self.active_downloads:
            download_item = self.active_downloads[download_id]
            download_item.status = DownloadStatus.CANCELLED

            # Cancel the future if it exists (non-blocking)
            if download_id in self.download_tasks:
                future = self.download_tasks[download_id]
                future.cancel()
                del self.download_tasks[download_id]

            # Move to completed (cancelled) list immediately
            del self.active_downloads[download_id]
            self.completed_downloads.append(download_item)
            if len(self.completed_downloads) > MAX_HISTORY:
                self.completed_downloads = self.completed_downloads[-MAX_HISTORY:]

            if self.progress_callback:
                self.progress_callback("download_cancelled", download_item)

    def retry_download(self, download_id: str) -> None:
        """Retry a failed download."""
        # Find in failed downloads
        download_item = None
        for item in self.failed_downloads:
            if item.id == download_id:
                download_item = item
                break

        if download_item:
            if self.progress_callback:
                self.progress_callback(
                    "log_message",
                    {"message": f"Retrying download: {download_item.title}"},
                )

            # Reset item status
            download_item.status = DownloadStatus.PENDING
            download_item.progress = 0.0
            download_item.error_message = ""

            # Remove from failed and add back to queue
            self.failed_downloads.remove(download_item)
            self.pending_queue.put(download_item)

            if self.progress_callback:
                self.progress_callback("download_retried", download_item)

    def remove_download(self, download_id: str, from_queue: str = "failed") -> None:
        """Remove a download from the specified queue."""
        if from_queue == "failed":
            self.failed_downloads = [
                item for item in self.failed_downloads if item.id != download_id
            ]
        elif from_queue == "completed":
            self.completed_downloads = [
                item for item in self.completed_downloads if item.id != download_id
            ]

        if self.progress_callback:
            self.progress_callback(
                "download_removed", {"id": download_id, "queue": from_queue}
            )

    def move_download_up(self, _: str) -> None:
        pass  # Python's Queue doesn't support reordering

    def move_download_down(self, _: str) -> None:
        pass  # Python's Queue doesn't support reordering

    def get_queue_status(self) -> dict[str, Any]:
        """Get current status of all queues."""
        return {
            "pending_count": self.pending_queue.qsize(),
            "active_count": len(self.active_downloads),
            "completed_count": len(self.completed_downloads),
            "failed_count": len(self.failed_downloads),
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "active_downloads": list(self.active_downloads.values()),
            "failed_downloads": self.failed_downloads,
            "completed_downloads": self.completed_downloads,
        }

    def _queue_manager(self) -> None:
        """Background thread that manages the download queue."""
        while (
            self.is_running
            and not self._stop_event.is_set()
            and not self._force_shutdown
        ):
            try:
                # Quick check for force shutdown
                if self._force_shutdown:  # pragma: no cover
                    break  # pragma: no cover

                # Check if we can start new downloads
                if (
                    not self.is_paused
                    and len(self.active_downloads)
                    < self.config.download.max_parallel_downloads
                ):
                    try:
                        # Get next item from queue (non-blocking)
                        download_item = self.pending_queue.get_nowait()
                        if not self._force_shutdown:
                            self._start_download(download_item)
                    except Empty:
                        pass

                # Quick shutdown check
                if self._force_shutdown:  # pragma: no cover
                    break  # pragma: no cover

                self._process_completed_tasks()

                # Block until woken by stop_event or 500 ms timeout
                self._stop_event.wait(timeout=0.5)
                if self._stop_event.is_set() or self._force_shutdown:
                    return

            except Exception as e:  # pragma: no cover
                print(f"Error in queue manager: {e}")  # pragma: no cover
                if self._force_shutdown:  # pragma: no cover
                    break  # pragma: no cover
                time.sleep(1)  # pragma: no cover

    def _process_completed_tasks(self) -> None:
        """Move finished download futures into completed or failed lists."""
        completed_tasks = [
            download_id
            for download_id, future in self.download_tasks.items()
            if future.done()
        ]

        for download_id in completed_tasks:
            if self._force_shutdown:  # pragma: no cover
                break  # pragma: no cover

            future = self.download_tasks.pop(download_id)
            if download_id in self.active_downloads:
                download_item = self.active_downloads.pop(download_id)

                try:
                    # Get the result (will raise exception if download failed)
                    future.result()
                    download_item.status = (
                        DownloadStatus.SKIPPED
                        if download_item.already_exists
                        else DownloadStatus.COMPLETED
                    )
                    download_item.completed_at = time.time()
                    self.completed_downloads.append(download_item)
                    if len(self.completed_downloads) > MAX_HISTORY:
                        self.completed_downloads = self.completed_downloads[
                            -MAX_HISTORY:
                        ]

                    if self.progress_callback:
                        self.progress_callback("download_completed", download_item)
                        res = (
                            f" [{download_item.resolution}]"
                            if download_item.resolution
                            else ""
                        )
                        self.progress_callback(
                            "log_message",
                            {
                                "message": f"Download completed: {download_item.title}{res}"
                            },
                        )

                except Exception as e:
                    download_item.error_message = str(e)
                    download_item.retry_count += 1

                    if download_item.retry_count <= self.config.download.retry_attempts:
                        # Retry the download
                        download_item.status = DownloadStatus.PENDING
                        download_item.progress = 0.0
                        self.pending_queue.put(download_item)

                        if self.progress_callback:
                            self.progress_callback("download_retrying", download_item)
                    else:
                        # Max retries reached, move to failed
                        download_item.status = DownloadStatus.FAILED
                        self.failed_downloads.append(download_item)
                        if len(self.failed_downloads) > MAX_HISTORY:
                            self.failed_downloads = self.failed_downloads[-MAX_HISTORY:]

                        if self.progress_callback:
                            self.progress_callback("download_failed", download_item)
                            self.progress_callback(
                                "log_message",
                                {
                                    "message": f"Download failed: {download_item.title} - "
                                    f"{download_item.error_message}"
                                },
                            )

    def _start_download(self, download_item: DownloadItem) -> None:
        """Start downloading a single item."""
        download_item.status = DownloadStatus.DOWNLOADING
        download_item.started_at = time.time()
        self.active_downloads[download_item.id] = download_item

        # Submit download task to executor
        future = self.executor.submit(self._download_worker, download_item)
        self.download_tasks[download_item.id] = future

        if self.progress_callback:
            self.progress_callback("download_started", download_item)
            self.progress_callback(
                "log_message", {"message": f"Starting download: {download_item.title}"}
            )

    def _make_ydl_logger(self, download_item: DownloadItem | None = None) -> Any:
        """Create a yt-dlp compatible logger object."""
        last_logged_percent = [-1]  # list used as mutable container for closure

        def logger(_: Any, msg: str | None) -> None:
            """Capture yt-dlp log output (yt-dlp passes self as first arg)."""
            if msg:
                import re

                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                clean_msg = ansi_escape.sub("", msg).strip()

                # Strip ETA from yt-dlp progress lines
                clean_msg = re.sub(r"\s+ETA\s+[\d:]+", "", clean_msg)

                # Convert speed units in log messages from MiB/s to Mbps
                if "MiB/s" in clean_msg:
                    try:
                        speed_match = re.search(r"(\d+\.?\d*)\s*MiB/s", clean_msg)
                        if speed_match:
                            speed_value = float(speed_match.group(1))
                            speed_mbps = speed_value * 8.388608
                            clean_msg = clean_msg.replace(
                                f"{speed_value}MiB/s", f"{speed_mbps:.1f}Mbps"
                            )
                            clean_msg = clean_msg.replace(
                                f"{speed_value} MiB/s", f"{speed_mbps:.1f} Mbps"
                            )
                    except Exception:  # pragma: no cover
                        clean_msg = clean_msg.replace("MiB/s", "Mbps")
                elif "KiB/s" in clean_msg:
                    try:
                        speed_match = re.search(r"(\d+\.?\d*)\s*KiB/s", clean_msg)
                        if speed_match:
                            speed_value = float(speed_match.group(1))
                            speed_mbps = speed_value * 0.008192
                            clean_msg = clean_msg.replace(
                                f"{speed_value}KiB/s", f"{speed_mbps:.1f}Mbps"
                            )
                            clean_msg = clean_msg.replace(
                                f"{speed_value} KiB/s", f"{speed_mbps:.1f} Mbps"
                            )
                    except Exception:  # pragma: no cover
                        clean_msg = clean_msg.replace("KiB/s", "Kbps")

                if download_item and "has already been downloaded" in clean_msg:
                    download_item.already_exists = True

                # Filter out excessive download progress lines - only log every 5%
                if clean_msg.startswith("[download]") and "%" in clean_msg:
                    try:
                        percent_str = clean_msg.split("%")[0].split()[-1]
                        current_percent = int(float(percent_str))
                        if (
                            current_percent % 5 == 0
                            and current_percent != last_logged_percent[0]
                        ):
                            last_logged_percent[0] = current_percent
                            if self.progress_callback:
                                self.progress_callback(
                                    "log_message", {"message": clean_msg}
                                )
                    except (ValueError, IndexError):
                        if self.progress_callback:
                            self.progress_callback(
                                "log_message", {"message": clean_msg}
                            )
                else:
                    if self.progress_callback:
                        self.progress_callback("log_message", {"message": clean_msg})

        log_obj = type(
            "Logger",
            (),
            {"debug": logger, "info": logger, "warning": logger, "error": logger},
        )()
        return log_obj

    def _make_progress_hook(
        self, download_item: DownloadItem
    ) -> Callable[[dict[str, Any]], None]:
        """Create a yt-dlp progress hook for the given download item."""
        last_milestone = [-1]  # mutable container for closure

        def progress_hook(d: dict[str, Any]) -> None:
            if d["status"] == "downloading":
                fragment_index = d.get("fragment_index")
                fragment_count = d.get("fragment_count")

                if (
                    fragment_index is not None
                    and fragment_count is not None
                    and fragment_count > 0
                ):
                    download_item.progress = (fragment_index / fragment_count) * 100.0
                else:
                    download_item.progress = d.get("_percent_str", "0%").replace(
                        "%", ""
                    )
                    try:
                        download_item.progress = float(download_item.progress)
                    except (ValueError, TypeError):
                        download_item.progress = 0.0

                import re

                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

                speed_str = d.get("_speed_str", "")
                speed_str = ansi_escape.sub("", speed_str).strip()

                if speed_str and "MiB/s" in speed_str:
                    try:
                        speed_value = float(speed_str.replace("MiB/s", "").strip())
                        speed_mbps = speed_value * 8.388608
                        download_item.speed = f"{speed_mbps:.1f} Mbps"
                    except (ValueError, TypeError):
                        download_item.speed = speed_str.replace("MiB/s", "Mbps")
                elif speed_str and "KiB/s" in speed_str:
                    try:
                        speed_value = float(speed_str.replace("KiB/s", "").strip())
                        speed_mbps = speed_value * 0.008192
                        download_item.speed = f"{speed_mbps:.1f} Mbps"
                    except (ValueError, TypeError):
                        download_item.speed = speed_str.replace("KiB/s", "Kbps")
                else:
                    download_item.speed = speed_str

                download_item.downloaded_bytes = d.get("downloaded_bytes", 0)
                download_item.total_bytes = d.get("total_bytes", 0) or d.get(
                    "total_bytes_estimate", 0
                )

                # Log progress at 25% milestones to the activity log
                pct = int(download_item.progress)
                milestone = (pct // 25) * 25
                if milestone > 0 and milestone != last_milestone[0]:
                    last_milestone[0] = milestone
                    speed_info = (
                        f" @ {download_item.speed}" if download_item.speed else ""
                    )
                    if self.progress_callback:
                        self.progress_callback(
                            "log_message",
                            {
                                "message": f"[{milestone}%] {download_item.title}{speed_info}"
                            },
                        )

                if self.progress_callback:
                    self.progress_callback("download_progress", download_item)

            elif d["status"] == "finished":
                download_item.progress = 100.0
                download_item.output_path = Path(d.get("filename", ""))
                info_dict = d.get("info_dict") or {}
                height = info_dict.get("height") or 0
                if height:
                    download_item.resolution = _height_to_label(
                        height, info_dict.get("width")
                    )

                if self.progress_callback:
                    self.progress_callback("download_progress", download_item)

        return progress_hook

    def _build_base_opts(
        self, download_item: DownloadItem, progress_hook: Any, log_obj: Any
    ) -> dict[str, Any]:
        """Assemble the base yt-dlp options dict shared across all download strategies."""
        base_opts: dict[str, Any] = {
            "outtmpl": str(
                self.config.download.download_directory / "%(title)s [%(id)s].%(ext)s"
            ),
            "progress_hooks": [progress_hook],
            "no_warnings": False,
            "logger": log_obj,
            "socket_timeout": 60,
            "retries": 2,
            "sleep_interval": 1,
            "max_sleep_interval": 5,
            "concurrent_fragment_downloads": 1,
            "nooverwrites": True,
        }
        # Required for harder n-challenges (e.g. members-only content).
        # Without this, yt-dlp falls back to clients that don't honour browser cookies.
        base_opts["remote_components"] = ["ejs:github"]
        if _get_js_runtime():
            base_opts["js_runtimes"] = _get_js_runtime()

        if self.config.download.audio_only:
            base_opts["format"] = (
                f"bestaudio[abr<={self.config.download.audio_quality}]/bestaudio/best"
            )
            base_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.config.download.audio_quality,
                }
            ]
        else:
            base_opts["format"] = self.config.download.video_quality

        if self.config.ytdl.write_info_json:
            base_opts["writeinfojson"] = True
        if self.config.ytdl.write_description:
            base_opts["writedescription"] = True
        if self.config.ytdl.embed_subs:
            base_opts["writesubtitles"] = True
            base_opts["writeautomaticsub"] = True
        if self.config.ytdl.add_metadata:
            base_opts["addmetadata"] = True

        ffmpeg_dir = _bundled_ffmpeg_dir()
        if ffmpeg_dir:
            base_opts["ffmpeg_location"] = ffmpeg_dir

        return base_opts

    def _log(self, message: str) -> None:
        """Send a line to the activity log, if anyone is listening."""
        if self.progress_callback:
            self.progress_callback("log_message", {"message": message})

    def _aborted(self, download_item: DownloadItem) -> bool:
        """True once the item was cancelled or all downloads were stopped."""
        return (
            download_item.status == DownloadStatus.CANCELLED
            or self._stop_event.is_set()
        )

    def _close_quietly(self, session: Any) -> None:
        """Close a yt-dlp session without letting cleanup fail a finished download.

        Closing writes the cookie jar back to a cookie file, which can fail
        (malformed or read-only file) after the download already succeeded.
        """
        try:
            session.close()
        except Exception as e:
            self._log(f"Could not close a yt-dlp session cleanly: {e}")

    def _access_modes(self) -> list[tuple[str, dict[str, Any]]]:
        """Every configured way to reach a video, in tie-break order."""
        browser = self.config.download.cookies_from_browser
        cookie_file = self.config.download.cookies_file
        modes: list[tuple[str, dict[str, Any]]] = []
        if browser:
            modes.append(
                (
                    f"signed in via {browser}",
                    {"cookiesfrombrowser": (browser, None, None, None)},
                )
            )
        modes.append(("signed out", {}))
        if cookie_file:
            modes.append(("cookie file", {"cookiefile": cookie_file}))
        return modes

    def _rank(self, info: dict[str, Any]) -> tuple[int, float, float]:
        """Rank one access mode's format selection for the current download type."""
        if self.config.download.audio_only:
            return _audio_rank(info)
        return _video_rank(info)

    def _probe_access_modes(
        self,
        download_item: DownloadItem,
        base_opts: dict[str, Any],
        sessions: contextlib.ExitStack,
    ) -> tuple[list[_Candidate], list[tuple[str, str]]]:
        """Extract the video once per access mode; a failing mode never blocks the rest.

        YouTube serves signed-in and signed-out sessions through different player
        clients, and which of them can see the top resolutions changes over time,
        so each mode's own format selection is kept for comparison (ADR 0003).
        """
        candidates: list[_Candidate] = []
        failures: list[tuple[str, str]] = []
        modes = self._access_modes()
        for label, mode_opts in modes:
            if self._aborted(download_item):
                break
            # Playlist entries stay unresolved here, so a playlist URL isn't
            # extracted in full once per mode before anything downloads.
            probe_opts = {**base_opts, **mode_opts, "extract_flat": "in_playlist"}
            if len(modes) > 1:
                probe_opts["logger"] = _ModeLogger(base_opts["logger"], label)
            try:
                session = _get_yt_dlp().YoutubeDL(probe_opts)  # type: ignore[arg-type]
                sessions.callback(self._close_quietly, session)
                info = session.extract_info(download_item.url, download=False)
                if not info:
                    raise Exception("yt-dlp returned no video information")
                rank = self._rank(info)
            except Exception as e:
                failures.append((label, str(e)))
                if "cookiesfrombrowser" in mode_opts and any(
                    marker in str(e).lower() for marker in _COOKIE_DB_ERRORS
                ):
                    self._log(
                        f"Could not extract cookies from "
                        f"{self.config.download.cookies_from_browser} "
                        "(close the browser and try again). Falling back..."
                    )
                continue
            candidates.append(_Candidate(label, mode_opts, session, info, rank))
        return candidates, failures

    def _no_access_error(self, failures: list[tuple[str, str]]) -> Exception:
        """Build the error raised when no access mode could extract the video."""
        has_cookie_source = bool(
            self.config.download.cookies_from_browser
            or self.config.download.cookies_file
        )
        if not has_cookie_source and any(
            keyword in message.lower()
            for _, message in failures
            for keyword in _AUTH_KEYWORDS
        ):
            return Exception(
                "This video requires YouTube login. "
                "Set a browser in Settings > Browser Cookies (recommended), "
                "or export a cookies.txt file."
            )
        return self._ytdlp_error(failures)

    @staticmethod
    def _ytdlp_error(failures: list[tuple[str, str]]) -> Exception:
        """Combine per-mode failures into one error, naming modes only if several."""
        if len(failures) == 1:
            return Exception(f"yt-dlp error: {failures[0][1]}")
        return Exception(
            "yt-dlp error: "
            + "; ".join(f"{label}: {message}" for label, message in failures)
        )

    def _rank_candidates(self, candidates: list[_Candidate]) -> list[_Candidate]:
        """Order candidates best first; equal ranks keep the configured mode order."""
        playlists = [c for c in candidates if c.is_playlist]
        if playlists:
            # Entries aren't resolved, so there is nothing to compare, and a mode
            # that sees the playlist beats one that fell back to a single video.
            return playlists
        # sorted() is stable, so equal ranks keep the configured mode order.
        ranked = sorted(candidates, key=lambda c: c.rank, reverse=True)
        if not self.config.download.audio_only:
            self._report_mode_disagreement(candidates, ranked[0])
        return ranked

    def _report_mode_disagreement(
        self, candidates: list[_Candidate], best: _Candidate
    ) -> None:
        """Say so when access modes offer different resolutions, so a gap is never silent."""
        if len({c.rank[0] for c in candidates}) < 2:
            return
        offers = "; ".join(
            f"{c.label} offers {_height_to_label(c.rank[0])}" for c in candidates
        )
        self._log(f"Quality check: {offers} - using {best.label}")

    @staticmethod
    def _output_video_height(session: Any, result: dict[str, Any] | None) -> int:
        """Resolution class of the video actually written to disk; 0 if unknown.

        Read with ffprobe from the finished file, not from yt-dlp's format
        metadata, so a mismatch between the two can be noticed.
        """
        paths = [
            d.get("filepath") for d in (result or {}).get("requested_downloads") or []
        ]
        paths = [path for path in paths if path and os.path.isfile(path)]
        if not paths:
            return 0
        from yt_dlp.postprocessor import FFmpegPostProcessor

        ffprobe = FFmpegPostProcessor(session)
        if not ffprobe.probe_available:
            return 0
        height = 0
        for path in paths:
            try:
                streams = ffprobe.get_metadata_object(path).get("streams") or []
            except Exception:
                continue
            for stream in streams:
                if stream.get("codec_type") != "video":
                    continue
                if (stream.get("disposition") or {}).get("attached_pic"):
                    continue  # embedded cover art, not the video
                height = max(
                    height,
                    _display_height(stream.get("height") or 0, stream.get("width")),
                )
        return height

    def _check_delivered_quality(
        self,
        download_item: DownloadItem,
        candidate: _Candidate,
        result: dict[str, Any] | None,
    ) -> None:
        """Warn if the file on disk is below the resolution that was selected."""
        if self.config.download.audio_only or candidate.is_playlist:
            return
        selected = candidate.rank[0]
        delivered = self._output_video_height(candidate.session, result)
        if delivered and delivered < selected:
            self._log(
                f"Quality warning: {download_item.title} was delivered at "
                f"{_height_to_label(delivered)} but {_height_to_label(selected)} "
                "was selected"
            )

    def _download_candidate(
        self,
        download_item: DownloadItem,
        candidate: _Candidate,
        base_opts: dict[str, Any],
        attempt: int,
    ) -> dict[str, Any] | None:
        """Download one access mode's result; return yt-dlp's processed info."""
        if candidate.is_playlist:
            # Let yt-dlp resolve and download entries one at a time, as before.
            opts = {**base_opts, **candidate.mode_opts}
            ydl = _get_yt_dlp().YoutubeDL(opts)  # type: ignore[arg-type]
            try:
                ydl.download([download_item.url])
            finally:
                self._close_quietly(ydl)
            return None
        result: dict[str, Any] | None
        if attempt == 0:
            # Reuses the probe's session and info dict: no second extraction.
            result = candidate.session.process_ie_result(candidate.info, download=True)
        else:
            # A fallback starts after an earlier attempt ran for a while; extract
            # again so its signed media URLs haven't expired.
            result = candidate.session.extract_info(download_item.url, download=True)
        return result

    def _download_best(
        self,
        download_item: DownloadItem,
        ranked: list[_Candidate],
        base_opts: dict[str, Any],
    ) -> None:
        """Download the best-ranked candidate, falling back down the ranking on failure."""
        from yt_dlp.utils import YoutubeDLError

        failures: list[tuple[str, str]] = []
        for index, candidate in enumerate(ranked):
            if self._aborted(download_item):
                return
            # A failed attempt may have flagged or labelled a different file.
            download_item.already_exists = False
            download_item.resolution = ""
            try:
                result = self._download_candidate(
                    download_item, candidate, base_opts, index
                )
            except YoutubeDLError as e:
                failures.append((candidate.label, str(e)))
                if index + 1 < len(ranked):
                    self._log(
                        f"Download via {candidate.label} failed - trying "
                        f"{ranked[index + 1].label}"
                    )
                continue
            self._check_delivered_quality(download_item, candidate, result)
            return
        raise self._ytdlp_error(failures)

    def _download_worker(self, download_item: DownloadItem) -> None:
        """Probe every access mode, then download the one offering the best quality."""
        log_obj = self._make_ydl_logger(download_item)
        progress_hook = self._make_progress_hook(download_item)
        base_opts = self._build_base_opts(download_item, progress_hook, log_obj)

        with contextlib.ExitStack() as sessions:
            candidates, failures = self._probe_access_modes(
                download_item, base_opts, sessions
            )
            if self._aborted(download_item):
                return
            if not candidates:
                raise self._no_access_error(failures)
            ranked = self._rank_candidates(candidates)
            self._download_best(download_item, ranked, base_opts)

    def __del__(self) -> None:
        """Cleanup when the manager is destroyed."""
        if hasattr(self, "is_running") and self.is_running:
            self._force_shutdown = True
            self._stop_event.set()
            if hasattr(self, "executor"):
                self.executor.shutdown(wait=False)
