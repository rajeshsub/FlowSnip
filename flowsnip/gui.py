"""
GUI module for FlowSnip using CustomTkinter.

Provides a modern, polished interface for managing video downloads with
queue management, progress tracking, and configuration options.
"""

import sys
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict

import customtkinter as ctk

from .config import Config
from .download_manager import DownloadItem, DownloadManager, DownloadStatus


class ProgressFrame(ctk.CTkFrame):
    """Frame for displaying download progress."""

    def __init__(self, parent, download_item: DownloadItem, download_manager, **kwargs):
        super().__init__(parent, **kwargs)

        self.download_item = download_item
        self.download_manager = download_manager
        self.setup_ui()

    def setup_ui(self):
        """Setup the progress UI elements."""
        # Title label
        title_text = self.download_item.title
        if len(title_text) > 60:
            title_text = title_text[:60] + "..."

        self.title_label = ctk.CTkLabel(self, text=title_text, anchor="w")
        self.title_label.grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 5)
        )

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5
        )
        self.progress_bar.set(0)

        # Status info
        self.status_label = ctk.CTkLabel(self, text="Status: Initializing", anchor="w")
        self.status_label.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=2
        )

        # Speed and ETA on next row
        self.speed_label = ctk.CTkLabel(self, text="Speed: --", anchor="w")
        self.speed_label.grid(row=3, column=0, sticky="ew", padx=10, pady=2)

        self.eta_label = ctk.CTkLabel(self, text="ETA: --", anchor="w")
        self.eta_label.grid(row=3, column=1, sticky="ew", padx=10, pady=2)

        # Action buttons
        self.cancel_button = ctk.CTkButton(
            self, text="Cancel", width=80, height=28, command=self.cancel_download
        )
        self.cancel_button.grid(row=4, column=1, sticky="e", padx=10, pady=(5, 10))

        # Configure grid weights
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def update_progress(self, download_item: DownloadItem):
        """Update the progress display."""
        self.download_item = download_item

        # Update progress bar
        self.progress_bar.set(download_item.progress / 100.0)

        # Update status - show Initializing if downloading but no progress yet
        if download_item.status == DownloadStatus.DOWNLOADING:
            if download_item.progress > 0:
                status_text = f"Status: Downloading ({download_item.progress:.1f}%)"
            else:
                status_text = "Status: Initializing..."
        else:
            status_text = f"Status: {download_item.status.value.title()}"
            if download_item.progress > 0 and download_item.status not in [
                DownloadStatus.COMPLETED,
                DownloadStatus.FAILED,
            ]:
                status_text += f" ({download_item.progress:.1f}%)"
        self.status_label.configure(text=status_text)

        # Update speed and ETA
        self.speed_label.configure(text=f"Speed: {download_item.speed or '--'}")

        # Format ETA with clearer units
        eta_display = download_item.eta or "--"
        if eta_display != "--" and ":" in eta_display:
            # Parse MM:SS or HH:MM:SS format
            parts = eta_display.split(":")
            if len(parts) == 2:
                # MM:SS format
                eta_display = f"{parts[0]}m {parts[1]}s"
            elif len(parts) == 3:
                # HH:MM:SS format
                eta_display = f"{parts[0]}h {parts[1]}m {parts[2]}s"
        self.eta_label.configure(text=f"ETA: {eta_display}")

        # Update button based on status
        if download_item.status in [DownloadStatus.COMPLETED, DownloadStatus.CANCELLED]:
            self.cancel_button.configure(text="Remove", command=self.remove_download)
        elif download_item.status == DownloadStatus.FAILED:
            self.cancel_button.configure(text="Retry", command=self.retry_download)

    def cancel_download(self):
        """Cancel this download."""
        if self.download_manager:
            self.download_manager.cancel_download(self.download_item.id)

    def remove_download(self):
        """Remove this download from the list."""
        print(f"ProgressFrame.remove_download called for {self.download_item.id}")
        print(f"Download status: {self.download_item.status}")

        if self.download_manager:
            print("Found download_manager")
            queue = (
                "failed"
                if self.download_item.status == DownloadStatus.FAILED
                else "completed"
            )
            print(f"Calling remove_download with queue={queue}")
            self.download_manager.remove_download(self.download_item.id, queue)
        else:
            print("ERROR: No download_manager found!")

    def retry_download(self):
        """Retry a failed download."""
        if self.download_manager:
            self.download_manager.retry_download(self.download_item.id)


class ConfigFrame(ctk.CTkFrame):
    """Frame for configuration settings."""

    def __init__(self, parent, config: Config, **kwargs):
        super().__init__(parent, **kwargs)
        self.config_obj = config
        self.setup_ui()

    def setup_ui(self):
        """Setup the configuration UI."""
        title_label = ctk.CTkLabel(
            self, text="Configuration", font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(10, 20))
        row = 1

        row = self._setup_browser_section(row)
        row = self._setup_download_section(row)
        row = self._setup_format_section(row)
        row = self._setup_appearance_section(row)
        self._setup_action_buttons(row)

        self.grid_columnconfigure(1, weight=1)

    def _setup_browser_section(self, row: int) -> int:
        """Add browser cookies dropdown and helper text."""
        ctk.CTkLabel(self, text="Browser Cookies\n(recommended):", justify="left").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.browser_var = ctk.StringVar(
            value=self.config_obj.download.cookies_from_browser or "Not set"
        )
        self.browser_dropdown = ctk.CTkOptionMenu(
            self,
            values=[
                "Not set",
                "chrome",
                "edge",
                "firefox",
                "brave",
                "opera",
                "chromium",
            ],
            variable=self.browser_var,
            command=self.update_browser_cookies,
            width=120,
        )
        self.browser_dropdown.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkLabel(
            self,
            text="Must be logged in to YouTube in that browser.\nNote: Close the browser before downloading for better reliability.",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))
        return row + 1

    def _setup_download_section(self, row: int) -> int:
        """Add auto-start, parallel slider, and download directory controls."""
        self.auto_start_var = ctk.BooleanVar(
            value=self.config_obj.ui.auto_start_downloads
        )
        self.auto_start_checkbox = ctk.CTkCheckBox(
            self,
            text="Auto-start",
            variable=self.auto_start_var,
            command=self.update_auto_start,
            width=100,
        )
        self.auto_start_checkbox.grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=5
        )
        row += 1

        slider_label_frame = ctk.CTkFrame(self)
        slider_label_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=5
        )
        ctk.CTkLabel(
            slider_label_frame, text="Max Parallel\nDownloads:", justify="left"
        ).pack(side="left", padx=5)
        slider_frame = ctk.CTkFrame(slider_label_frame)
        slider_frame.pack(side="left", fill="x", expand=True)
        self.parallel_slider = ctk.CTkSlider(
            slider_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            command=self.update_parallel_downloads,
            width=120,
        )
        self.parallel_slider.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.parallel_value_label = ctk.CTkLabel(
            slider_frame,
            text=str(self.config_obj.download.max_parallel_downloads),
            width=30,
        )
        self.parallel_value_label.pack(side="right", padx=5, pady=5)
        row += 1

        ctk.CTkLabel(self, text="Download Directory:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        dir_frame = ctk.CTkFrame(self)
        dir_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.download_dir_label = ctk.CTkLabel(
            dir_frame, text=str(self.config_obj.download.download_directory), width=168
        )
        self.download_dir_label.pack(side="left", fill="x", expand=True)
        browse_btn = ctk.CTkButton(
            dir_frame, text="Browse", command=self.browse_directory, width=60
        )
        browse_btn.pack(side="right", padx=5)
        return row + 1

    def _setup_format_section(self, row: int) -> int:
        """Add audio-only toggle, video quality, and audio quality controls."""
        self.audio_only_var = ctk.BooleanVar(value=self.config_obj.download.audio_only)
        self.audio_only_checkbox = ctk.CTkCheckBox(
            self,
            text="Audio Only",
            variable=self.audio_only_var,
            command=self.on_audio_only_toggle,
        )
        self.audio_only_checkbox.grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=5
        )
        row += 1

        ctk.CTkLabel(self, text="Video Quality:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.quality_options = {
            "Best Quality": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "8K (4320p)": "bestvideo[height<=4320][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=4320]+bestaudio/best[ext=mp4]/best",
            "4K (2160p)": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[ext=mp4]/best",
            "1440p": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[ext=mp4]/best",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best",
            "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[ext=mp4][height<=720]/best[height<=720]",
            "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[ext=mp4][height<=480]/best[height<=480]",
            "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[ext=mp4][height<=360]/best[height<=360]",
            "240p": "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=240]+bestaudio/best[ext=mp4][height<=240]/best[height<=240]",
        }
        current_format = self.config_obj.download.video_quality
        current_display = "Best Quality"
        for display_name, format_string in self.quality_options.items():
            if format_string == current_format:
                current_display = display_name
                break
        self.quality_var = ctk.StringVar(value=current_display)
        self.quality_combobox = ctk.CTkOptionMenu(
            self,
            values=list(self.quality_options.keys()),
            command=self.update_video_quality,
            variable=self.quality_var,
        )
        self.quality_combobox.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        self.quality_combobox.configure(
            state="disabled" if self.audio_only_var.get() else "normal"
        )
        row += 1

        self.audio_quality_var = ctk.StringVar(
            value=self.config_obj.download.audio_quality
        )
        self.audio_quality_label = ctk.CTkLabel(self, text="Audio Quality:")
        self.audio_quality_combobox = ctk.CTkOptionMenu(
            self,
            values=["best", "320", "256", "192", "128", "96"],
            command=self.update_audio_quality,
        )
        self.audio_quality_combobox.set(self.config_obj.download.audio_quality)
        self.audio_quality_row = row
        self.toggle_audio_quality_visibility()
        return row + 1

    def _setup_appearance_section(self, row: int) -> int:
        """Add theme selector."""
        ctk.CTkLabel(self, text="Theme:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.theme_var = ctk.StringVar(value=self.config_obj.ui.theme)
        self.theme_combobox = ctk.CTkOptionMenu(
            self,
            values=["light", "dark", "auto"],
            command=self.update_theme,
            variable=self.theme_var,
        )
        self.theme_combobox.set(self.config_obj.ui.theme)
        self.theme_combobox.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        return row + 1

    def _setup_action_buttons(self, row: int) -> None:
        """Add Save Config and Load Config buttons."""
        button_frame = ctk.CTkFrame(self)
        button_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=20
        )

        save_button = ctk.CTkButton(
            button_frame, text="Save Config", command=self.save_config
        )
        save_button.pack(side="left", padx=5)

        load_button = ctk.CTkButton(
            button_frame, text="Load Config", command=self.load_config
        )
        load_button.pack(side="right", padx=5)

    def on_audio_only_toggle(self):
        self.update_audio_only()
        # Disable/enable video quality combobox
        if self.audio_only_var.get():
            self.quality_combobox.configure(state="disabled")
        else:
            self.quality_combobox.configure(state="normal")

    def toggle_audio_quality_visibility(self):
        """Show or hide audio quality controls based on audio_only setting."""
        if self.audio_only_var.get():
            # Show audio quality controls
            self.audio_quality_label.grid(
                row=self.audio_quality_row, column=0, sticky="w", padx=10, pady=5
            )
            self.audio_quality_combobox.grid(
                row=self.audio_quality_row, column=1, sticky="ew", padx=10, pady=5
            )
        else:
            # Hide audio quality controls
            self.audio_quality_label.grid_remove()
            self.audio_quality_combobox.grid_remove()

    def browse_directory(self):
        """Browse for download directory."""
        directory = filedialog.askdirectory(
            title="Select Download Directory",
            initialdir=str(self.config_obj.download.download_directory),
        )
        if directory:
            self.config_obj.download.download_directory = Path(directory)
            self.download_dir_label.configure(text=str(directory))

    def update_parallel_downloads(self, value):
        """Update max parallel downloads."""
        int_value = int(value)
        self.config_obj.download.max_parallel_downloads = int_value
        self.parallel_value_label.configure(text=str(int_value))

    def update_video_quality(self, selected_display_name):
        """Update video quality setting."""
        format_string = self.quality_options.get(
            selected_display_name, "bestvideo+bestaudio/best"
        )
        self.config_obj.download.video_quality = format_string

    def update_audio_only(self):
        """Update audio only setting."""
        self.config_obj.download.audio_only = self.audio_only_var.get()
        self.toggle_audio_quality_visibility()

    def update_audio_quality(self, value):
        """Update audio quality setting."""
        self.config_obj.download.audio_quality = value

    def update_theme(self, value):
        """Update UI theme."""
        self.config_obj.ui.theme = value
        ctk.set_appearance_mode(value)

    def update_auto_start(self):
        """Update auto-start downloads setting."""
        self.config_obj.ui.auto_start_downloads = self.auto_start_var.get()

    def save_config(self):
        """Save configuration to file."""
        try:
            file_path = filedialog.asksaveasfilename(
                title="Save Configuration",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if file_path:
                self.config_obj.save_to_file(file_path)
                messagebox.showinfo("Success", "Configuration saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")

    def load_config(self):
        """Load configuration from file."""
        try:
            file_path = filedialog.askopenfilename(
                title="Load Configuration",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if file_path:
                new_config = Config.load_from_file(file_path)
                self.config_obj.download = new_config.download
                self.config_obj.ui = new_config.ui
                self.config_obj.ytdl = new_config.ytdl

                self.update_ui_from_config()
                messagebox.showinfo("Success", "Configuration loaded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")

    def update_browser_cookies(self, value: str):
        """Update the browser-cookies setting."""
        self.config_obj.download.cookies_from_browser = (
            None if value == "Not set" else value
        )

    def update_ui_from_config(self):
        """Update UI elements from current config."""
        self.download_dir_label.configure(
            text=str(self.config_obj.download.download_directory)
        )
        self.parallel_slider.set(self.config_obj.download.max_parallel_downloads)
        self.parallel_value_label.configure(
            text=str(self.config_obj.download.max_parallel_downloads)
        )
        current_format = self.config_obj.download.video_quality
        current_display = "Best Quality"
        for display_name, format_string in self.quality_options.items():
            if format_string == current_format:
                current_display = display_name
                break
        self.quality_var.set(current_display)
        self.audio_only_var.set(self.config_obj.download.audio_only)
        self.audio_quality_combobox.set(self.config_obj.download.audio_quality)
        self.toggle_audio_quality_visibility()
        self.auto_start_var.set(self.config_obj.ui.auto_start_downloads)
        self.browser_var.set(self.config_obj.download.cookies_from_browser or "Not set")


class FlowSnipGUI:
    """Main GUI application class."""

    def show_section(self, section):
        """Show the selected section in the main content area."""
        self.downloads_scroll.grid_remove()
        self.config_frame.grid_remove()
        self.stats_frame.grid_remove()
        if section == "Downloads":
            self.downloads_scroll.grid(row=0, column=0, sticky="nsew")
        elif section == "Configuration":
            self.config_frame.grid(row=0, column=0, sticky="nsew")
        elif section == "Statistics":
            self.stats_frame.grid(row=0, column=0, sticky="nsew")

    def __init__(self, config: Config):
        """Initialize the GUI application."""
        self.config = config
        self.download_manager = DownloadManager(config, self.progress_callback)
        self.progress_frames: Dict[str, ProgressFrame] = {}
        self._last_ui_update: Dict[str, float] = {}
        self._log_line_count = 0

        # Setup the main window
        self.setup_window()
        self.setup_ui()

        # Show legal disclaimer after the window has rendered
        self.root.after(150, self._show_disclaimer_modal)

        # Start download manager if auto-start is enabled
        if self.config.ui.auto_start_downloads:
            self.download_manager.start_downloads()

    def setup_window(self):
        """Setup the main window."""
        ctk.set_appearance_mode(self.config.ui.theme)
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("FlowSnip - Media Downloader")
        self.root.geometry(
            f"{self.config.ui.window_width}x{self.config.ui.window_height}"
        )
        self.root.minsize(800, 600)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)

    def _show_disclaimer_modal(self):
        """Show the legal disclaimer after the window has rendered."""
        result = messagebox.askyesno(
            "Legal Disclaimer - FlowSnip",
            "FlowSnip is a tool for accessing content you own or have a legal right to access.\n\n"
            "You are solely responsible for:\n"
            "• Ensuring compliance with platform terms of service\n"
            "• Respecting copyright and intellectual property laws\n\n"
            "Maintainers assume NO LIABILITY for legal violations or misuse.\n\n"
            "For full details, see DISCLAIMER.md.\n\nDo you agree to these terms?",
        )
        if not result:
            messagebox.showinfo(
                "Terminated",
                "You did not agree to the terms. FlowSnip will now exit.",
            )
            sys.exit(0)

    def setup_ui(self):
        """Setup the user interface — URL bar first, rest deferred."""
        t0 = time.perf_counter()
        self._setup_url_bar()
        self.root.after(0, self._finish_ui_setup)
        print(f"[timing] setup_ui initial: {time.perf_counter() - t0:.3f}s")

    def _finish_ui_setup(self):
        """Complete UI setup scheduled after the initial frame renders."""
        t0 = time.perf_counter()
        self._setup_sidebar()
        self._setup_downloads_area()
        self._setup_log_panel()
        self.update_button_states()
        print(f"[timing] setup_ui complete: {time.perf_counter() - t0:.3f}s")

    def _setup_url_bar(self):
        """Build the top URL input bar with action buttons."""
        top_frame = ctk.CTkFrame(self.root)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(top_frame, text="Media URLs:").grid(
            row=0, column=0, padx=10, pady=10, sticky="n"
        )
        self.url_textbox = ctk.CTkTextbox(top_frame, height=160, width=320)
        self.url_textbox.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 0))
        self.url_textbox.insert(
            "1.0",
            "Enter one media URL per line (YouTube, Vimeo, Twitch, Instagram, etc.)",
        )
        self.url_textbox.bind("<FocusIn>", lambda e: self._clear_url_placeholder())
        self.url_textbox.bind("<FocusOut>", lambda e: self._restore_url_placeholder())
        self.url_textbox.bind(
            "<KeyRelease>", lambda e: self._check_start_button_state()
        )
        ctk.CTkLabel(
            top_frame,
            text="One URL per line.",
            font=ctk.CTkFont(size=12),
            text_color="#888",
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(0, 8))

        button_frame = ctk.CTkFrame(top_frame)
        button_frame.grid(row=0, column=2, padx=10, pady=10)

        self.start_button = ctk.CTkButton(
            button_frame, text="Start", command=self.start_downloads
        )
        self.start_button.pack(side="left", padx=5)

        self.pause_button = ctk.CTkButton(
            button_frame, text="Pause", command=self.pause_downloads
        )
        self.pause_button.pack(side="left", padx=5)

        self.stop_button = ctk.CTkButton(
            button_frame, text="Stop", command=self.stop_downloads
        )
        self.stop_button.pack(side="left", padx=5)

        self.open_folder_button = ctk.CTkButton(
            button_frame,
            text="Open Downloads Folder",
            command=self.open_downloads_folder,
        )
        self.open_folder_button.pack(side="left", padx=5)

    def _setup_sidebar(self):
        """Build the left sidebar containing the configuration panel."""
        main_frame = ctk.CTkFrame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main_frame.grid_columnconfigure(0, weight=0)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(main_frame, width=180)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10), pady=0)

        self.config_frame = ConfigFrame(sidebar, self.config)
        self.config_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.content_frame = ctk.CTkFrame(main_frame)
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=0)
        self.content_frame.grid_columnconfigure(0, weight=1)

    def _setup_downloads_area(self):
        """Build the scrollable downloads list and statistics panel below it."""
        self.downloads_scroll = ctk.CTkScrollableFrame(self.content_frame)
        self.downloads_scroll.grid(
            row=0, column=0, sticky="nsew", padx=10, pady=(10, 5)
        )
        self.downloads_scroll.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            self.downloads_scroll, text="No active downloads"
        )
        self.status_label.grid(row=0, column=0, pady=6)

        self.stats_frame = ctk.CTkFrame(self.content_frame)
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
        self.setup_stats_tab(self.stats_frame)

    def _setup_log_panel(self):
        """Build the activity log panel at the bottom."""
        log_frame = ctk.CTkFrame(self.root)
        log_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        log_label = ctk.CTkLabel(log_frame, text="Activity Log:", anchor="w")
        log_label.grid(row=0, column=0, sticky="w", padx=10, pady=(5, 0))

        self.log_textbox = ctk.CTkTextbox(log_frame, height=120, wrap="none")
        self.log_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.log_textbox.configure(state="disabled")

        self.log_textbox.bind("<Button-3>", self.show_log_context_menu)

    def setup_stats_tab(self, stats_frame):
        """Setup the statistics section."""
        title_label = ctk.CTkLabel(
            stats_frame,
            text="Download Statistics",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title_label.pack(pady=(10, 20))

        self.stats_labels = {}
        stats_info = [
            ("active", "Active Downloads"),
            ("completed", "Completed Downloads"),
            ("failed", "Failed Downloads"),
            ("total", "Total Downloads"),
        ]
        for key, label in stats_info:
            frame = ctk.CTkFrame(stats_frame)
            frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(frame, text=f"{label}:", anchor="w").pack(
                side="left", padx=10, pady=10
            )
            self.stats_labels[key] = ctk.CTkLabel(frame, text="0", anchor="e")
            self.stats_labels[key].pack(side="right", padx=10, pady=10)
        self.update_stats()

    def add_download(self, event=None):
        """Add download(s) from URL textbox."""
        urls_text = self.url_textbox.get("1.0", "end").strip()
        if not urls_text or urls_text == "Enter one video URL per line":
            messagebox.showwarning("Warning", "Please enter a URL")
            return
        urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
        if urls:
            for url in urls:
                self.download_manager.add_download(url)
            self.url_textbox.delete("1.0", "end")
            if (
                self.config.ui.auto_start_downloads
                and not self.download_manager.is_running
            ):
                self.download_manager.start_downloads()
                self.update_button_states()
        else:  # pragma: no cover
            messagebox.showwarning("Warning", "No valid URLs found")  # pragma: no cover

    def _clear_url_placeholder(self):
        if self.url_textbox.get("1.0", "end").strip().startswith("Enter one media"):
            self.url_textbox.delete("1.0", "end")

    def _restore_url_placeholder(self):
        if not self.url_textbox.get("1.0", "end").strip():
            self.url_textbox.insert(
                "1.0",
                "Enter one media URL per line (YouTube, Twitch, Twitter/x, Facebook, Instagram, etc.)",
            )

    def _check_start_button_state(self):
        """Enable start button if there's text in the URL box, even if downloads are in progress."""
        urls_text = self.url_textbox.get("1.0", "end").strip()
        has_urls = urls_text and urls_text != "Enter one video URL per line"
        if has_urls:
            self.start_button.configure(state="normal", text="Start")

    def log_message(self, message: str):
        """Add a message to the log window."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
        self._log_line_count += 1
        if self._log_line_count > 1000:
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "100.0")
            self.log_textbox.configure(state="disabled")
            self._log_line_count -= 100

    def show_log_context_menu(self, event):
        """Show context menu for the activity log."""
        import tkinter as tk

        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="Copy All", command=self.copy_log_contents)
        context_menu.add_command(label="Clear Log", command=self.clear_log)

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def copy_log_contents(self):
        """Copy all log contents to clipboard."""
        log_contents = self.log_textbox.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(log_contents)

    def clear_log(self):
        """Clear all log contents."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def start_downloads(self):
        """Start the download manager and add URLs from textbox if present."""
        urls_text = self.url_textbox.get("1.0", "end").strip()

        if urls_text and urls_text != "Enter one video URL per line":
            urls = [line.strip() for line in urls_text.splitlines() if line.strip()]

            if urls:
                self.url_textbox.delete("1.0", "end")
                self.start_button.configure(state="disabled", text="Adding...")

                import threading

                def add_urls_async():
                    self.download_manager.add_multiple_downloads(urls)
                    self.root.after(
                        0,
                        lambda: self.start_button.configure(
                            state="normal", text="Start"
                        ),
                    )

                threading.Thread(target=add_urls_async, daemon=True).start()

        if not self.download_manager.is_running:
            self.download_manager.start_downloads()
            self.update_button_states()

    def pause_downloads(self):
        """Pause downloads."""
        if self.download_manager.is_paused:
            self.download_manager.resume_downloads()
        else:
            self.download_manager.pause_downloads()
        self.update_button_states()

    def stop_downloads(self):
        """Stop all downloads."""
        import threading

        def stop_async():
            self.download_manager.stop_downloads()
            self.root.after(0, self.update_button_states)

        self.stop_button.configure(state="disabled", text="Stopping...")
        threading.Thread(target=stop_async, daemon=True).start()

    def open_downloads_folder(self):
        """Open the downloads folder in the system file explorer."""
        import platform
        import subprocess

        download_dir = self.config.download.download_directory

        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", str(download_dir)])
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(download_dir)])
            else:
                subprocess.run(["xdg-open", str(download_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open downloads folder: {str(e)}")

    def update_button_states(self):
        """Update button states based on download manager status."""
        if self.download_manager.is_running:
            self.start_button.configure(state="disabled")
            self.pause_button.configure(state="normal")
            self.stop_button.configure(state="normal")

            if self.download_manager.is_paused:
                self.pause_button.configure(text="Resume")
            else:
                self.pause_button.configure(text="Pause")
        else:
            self.start_button.configure(state="normal")
            self.pause_button.configure(state="disabled", text="Pause")
            self.stop_button.configure(state="disabled")

    def progress_callback(self, event_type: str, data):
        """Callback for download progress updates."""
        if event_type == "download_progress":
            now = time.monotonic()
            item_id = data.id
            if now - self._last_ui_update.get(item_id, 0) < 0.1:
                return
            self._last_ui_update[item_id] = now
        self.root.after(0, self._update_ui_callback, event_type, data)

    def _update_ui_callback(self, event_type: str, data):
        """Update UI callback that runs in main thread."""
        if event_type == "download_added":
            self.add_progress_frame(data)
        elif event_type in [
            "download_started",
            "download_progress",
            "download_completed",
            "download_failed",
        ]:
            self.update_progress_frame(data)
        elif event_type == "download_cancelled":
            self.remove_progress_frame(data.id)
        elif event_type == "download_removed":
            self.remove_progress_frame(data["id"])
        elif event_type == "log_message":
            self.log_message(data["message"])

        if event_type != "log_message":
            self.update_status_display()
            self.update_button_states()

    def add_progress_frame(self, download_item: DownloadItem):
        """Add a progress frame for a new download."""
        if download_item.id not in self.progress_frames:
            if hasattr(self, "status_label") and self.status_label.winfo_exists():
                self.status_label.destroy()

            progress_frame = ProgressFrame(
                self.downloads_scroll, download_item, self.download_manager
            )
            progress_frame.grid(
                row=len(self.progress_frames), column=0, sticky="ew", padx=5, pady=5
            )
            self.progress_frames[download_item.id] = progress_frame

    def update_progress_frame(self, download_item: DownloadItem):
        """Update an existing progress frame."""
        if download_item.id in self.progress_frames:
            self.progress_frames[download_item.id].update_progress(download_item)

    def remove_progress_frame(self, download_id: str):
        """Remove a progress frame."""
        print(f"GUI: Removing progress frame for {download_id}")
        print(f"Current progress_frames keys: {list(self.progress_frames.keys())}")

        if download_id in self.progress_frames:
            self.progress_frames[download_id].destroy()
            del self.progress_frames[download_id]

            for i, frame in enumerate(self.progress_frames.values()):
                frame.grid(row=i, column=0, sticky="ew", padx=5, pady=5)

            if not self.progress_frames:
                self.status_label = ctk.CTkLabel(
                    self.downloads_scroll, text="No downloads"
                )
                self.status_label.grid(row=0, column=0, pady=20)

    def update_status_display(self):
        """Update the status display."""
        status = self.download_manager.get_queue_status()

        active_count = status["active_count"]
        if active_count > 0:
            self.root.title(f"FlowSnip - {active_count} downloading")
        else:
            self.root.title("FlowSnip - Media Downloader")

    def update_stats(self):
        """Update statistics display."""
        status = self.download_manager.get_queue_status()

        self.stats_labels["active"].configure(text=str(status["active_count"]))
        self.stats_labels["completed"].configure(text=str(status["completed_count"]))
        self.stats_labels["failed"].configure(text=str(status["failed_count"]))

        total = (
            status["pending_count"]
            + status["active_count"]
            + status["completed_count"]
            + status["failed_count"]
        )
        self.stats_labels["total"].configure(text=str(total))

        interval = 1000 if status["active_count"] > 0 else 5000
        self.root.after(interval, self.update_stats)

    def run(self):
        """Start the GUI application."""
        try:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.mainloop()
        except Exception as e:
            print(f"GUI error: {e}")
            self.cleanup()

    def on_closing(self):
        """Handle application closing."""
        try:
            self.download_manager.is_running = False
            self.download_manager._stop_event.set()

            for download_id in list(self.download_manager.active_downloads.keys()):
                self.download_manager.cancel_download(download_id)

            self.download_manager.executor.shutdown(wait=False)

            geometry = self.root.geometry()
            if geometry and isinstance(geometry, str) and "x" in geometry:
                size_part = geometry.split("+")[0]
                width, height = map(int, size_part.split("x"))
                self.config.ui.window_width = width
                self.config.ui.window_height = height

            from .config import get_default_config_path

            self.config.save_to_file(get_default_config_path())

        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            self.root.destroy()

    def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, "download_manager"):
            self.download_manager.stop_downloads()
