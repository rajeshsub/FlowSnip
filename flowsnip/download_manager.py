"""
Download manager for FlowSnip.

Handles parallel downloads, queue management, and error handling for yt-dlp operations.
"""

from __future__ import annotations

import os
import shutil
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

    # Prefer Node.js — check PATH first, then common Windows install locations.
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


# Lazy accessors — avoid import-time cost of loading yt_dlp and probing the filesystem.
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


def _height_to_label(height: int) -> str:
    """Convert pixel height to a human-readable resolution label."""
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
        # Attempt 1: browser cookies (includes PO token — best for YouTube)
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

                # Filter out excessive download progress lines — only log every 5%
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
                height = (d.get("info_dict") or {}).get("height") or 0
                if height:
                    download_item.resolution = _height_to_label(height)

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

        return base_opts

    def _run_ydl(self, download_item: DownloadItem, opts: dict) -> None:
        """Execute a single yt-dlp download attempt with the given options."""
        from yt_dlp.utils import DownloadError, ExtractorError

        try:
            with _get_yt_dlp().YoutubeDL(opts) as ydl:  # type: ignore[arg-type]
                ydl.download([download_item.url])
        except (DownloadError, ExtractorError) as e:
            raise Exception(f"yt-dlp error: {e}")

    def _download_worker(self, download_item: DownloadItem) -> None:
        """Coordinator that tries each download strategy in priority order."""
        log_obj = self._make_ydl_logger(download_item)
        progress_hook = self._make_progress_hook(download_item)
        base_opts = self._build_base_opts(download_item, progress_hook, log_obj)

        # Strategy A: browser cookies (highest priority).
        # yt-dlp extracts PO tokens directly from the browser session, bypassing bot checks.
        if self.config.download.cookies_from_browser:
            opts_browser = {
                **base_opts,
                "cookiesfrombrowser": (
                    self.config.download.cookies_from_browser,
                    None,
                    None,
                    None,
                ),
            }
            try:
                self._run_ydl(download_item, opts_browser)
                return
            except Exception as e:
                msg = str(e).lower()
                if "could not copy" in msg or "database" in msg or "locked" in msg:
                    if self.progress_callback:
                        self.progress_callback(
                            "log_message",
                            {
                                "message": f"Could not extract cookies from "
                                f"{self.config.download.cookies_from_browser} "
                                "(close the browser and try again). Falling back..."
                            },
                        )
                elif not any(kw in msg for kw in _AUTH_KEYWORDS):
                    raise

        # Strategy B: default yt-dlp with Firefox user-agent — works for most public videos.
        opts_public = {
            **base_opts,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        }
        try:
            self._run_ydl(download_item, opts_public)
            return
        except Exception as e:
            msg = str(e).lower()
            if not any(kw in msg for kw in _AUTH_KEYWORDS):
                raise

        # Strategy C: cookie file for auth-required content.
        if not self.config.download.cookies_file:
            raise Exception(
                "This video requires YouTube login. "
                "Set a browser in Settings > Browser Cookies (recommended), "
                "or export a cookies.txt file."
            )
        if self.progress_callback:
            self.progress_callback(
                "log_message",
                {"message": "Auth required — retrying with cookie file..."},
            )
        opts_cookiefile = {**base_opts, "cookiefile": self.config.download.cookies_file}
        self._run_ydl(download_item, opts_cookiefile)

    def __del__(self) -> None:
        """Cleanup when the manager is destroyed."""
        if hasattr(self, "is_running") and self.is_running:
            self._force_shutdown = True
            self._stop_event.set()
            if hasattr(self, "executor"):
                self.executor.shutdown(wait=False)
