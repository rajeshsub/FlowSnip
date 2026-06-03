"""
FlowSnip: A modern GUI wrapper for yt-dlp with advanced download management.

This package provides a comprehensive interface for managing video downloads
with features like parallel processing, queue management, and error handling.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("flowsnip")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"

__author__ = "Rajesh Subramanian"

from .config import Config, UpdateConfig
from .download_manager import DownloadItem, DownloadManager, DownloadStatus

__all__ = ["Config", "UpdateConfig", "DownloadManager", "DownloadItem", "DownloadStatus"]
