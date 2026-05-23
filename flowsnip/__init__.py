"""
FlowSnip: A modern GUI wrapper for yt-dlp with advanced download management.

This package provides a comprehensive interface for managing video downloads
with features like parallel processing, queue management, and error handling.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .config import Config
from .download_manager import DownloadItem, DownloadManager, DownloadStatus

__all__ = ["Config", "DownloadManager", "DownloadItem", "DownloadStatus"]
