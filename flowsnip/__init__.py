"""
FlowSnip: A modern GUI wrapper for yt-dlp with advanced download management.

This package provides a comprehensive interface for managing video downloads
with features like parallel processing, queue management, and error handling.
"""

__version__ = "0.1.0"
__author__ = "Rajesh Subramaniam"
__email__ = ""

from .config import Config, UpdateConfig
from .download_manager import DownloadItem, DownloadManager, DownloadStatus

__all__ = ["Config", "UpdateConfig", "DownloadManager", "DownloadItem", "DownloadStatus"]
