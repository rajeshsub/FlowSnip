"""About dialog for FlowSnip: version, dependencies, and a link to the project."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Any

import customtkinter as ctk
from yt_dlp.version import __version__ as ytdlp_version

from . import __version__

PROJECT_URL = "https://github.com/rajeshsub/FlowSnip"

_UNKNOWN_VERSION = "unknown"


class AboutDialog(ctk.CTkToplevel):
    """Modal window showing what is running and where to find the project."""

    def __init__(self, master: Any) -> None:
        super().__init__(master)
        self.title("About FlowSnip")
        self.resizable(False, False)

        ctk.CTkLabel(
            self, text="FlowSnip", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(padx=40, pady=(24, 4))
        if __version__ != _UNKNOWN_VERSION:
            ctk.CTkLabel(self, text=f"Version {__version__}").pack()
        ctk.CTkLabel(self, text=f"yt-dlp {ytdlp_version}").pack()
        ctk.CTkLabel(self, text="A GUI wrapper for yt-dlp.\nMIT License.").pack(
            padx=40, pady=12
        )
        ctk.CTkLabel(self, text=PROJECT_URL).pack()

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(pady=(16, 24))
        ctk.CTkButton(
            buttons,
            text="GitHub",
            width=100,
            command=lambda: webbrowser.open(PROJECT_URL),
        ).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Close", width=100, command=self.destroy).pack(
            side="left", padx=6
        )

        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(master)
        self.after(50, self._take_focus)

    def _take_focus(self) -> None:
        """Make the dialog modal once it is on screen.

        Grabbing before the window is mapped fails on X11, and the user may
        have closed the dialog within the delay, so both are tolerated.
        """
        try:
            if self.winfo_exists():
                self.grab_set()
                self.focus_force()
        except tk.TclError:
            pass
