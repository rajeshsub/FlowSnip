"""
Main entry point for FlowSnip application.

This module handles command-line argument parsing, configuration loading,
and application startup.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flowsnip import __version__, updater
from flowsnip.config import Config, create_arg_parser, get_default_config_path

if TYPE_CHECKING:
    from flowsnip.gui import FlowSnipGUI
else:
    FlowSnipGUI: Any = None


def _get_gui_class() -> Any:
    """Return the GUI class without importing tkinter until the GUI path is used."""
    if FlowSnipGUI is not None:
        return FlowSnipGUI

    try:
        from flowsnip.gui import FlowSnipGUI as gui_class
    except ModuleNotFoundError as exc:
        if exc.name in {"tkinter", "customtkinter"}:
            print(
                "FlowSnip GUI requires tkinter/customtkinter. "
                "Install the system Tk package, for example on Fedora: "
                "sudo dnf install python3-tkinter"
            )
            raise RuntimeError("GUI dependencies are not installed") from exc
        raise

    globals()["FlowSnipGUI"] = gui_class
    return gui_class


def _apply_ytdlp_update(app: Any, new_ytdlp: str) -> None:
    """Run yt-dlp in-place upgrade and post result banner back to the GUI thread."""
    success = updater.update_ytdlp()
    msg = (
        f"yt-dlp updated to {new_ytdlp}. Restart FlowSnip to use it."
        if success
        else "yt-dlp update failed - check your connection."
    )
    app.root.after(
        0,
        lambda m=msg: app.show_update_banner(m, "OK", app._dismiss_update_banner),
    )


def _run_update_checks(app: Any, config: Config, config_path: Path | str) -> None:
    """Background thread: check for FlowSnip and yt-dlp updates."""
    cfg = config.updates

    if not updater.should_check(cfg.last_checked, cfg.frequency):
        return

    new_version = None
    if cfg.check_flowsnip:
        new_version = updater.check_flowsnip_update(__version__)
        if new_version:
            url = f"https://github.com/rajeshsub/FlowSnip/releases/tag/{new_version}"
            app.root.after(
                0,
                lambda: app.show_update_banner(
                    f"FlowSnip {new_version} is available.",
                    "Download",
                    lambda: webbrowser.open(url),
                ),
            )

    if cfg.check_ytdlp:
        from yt_dlp.version import __version__ as current_ytdlp

        new_ytdlp = updater.check_ytdlp_update(current_ytdlp)
        if new_ytdlp and updater.is_frozen():
            # A packaged build can't pip-install into itself; yt-dlp only
            # changes with a FlowSnip release. A FlowSnip banner already says so.
            if not new_version:
                app.root.after(
                    0,
                    lambda v=new_ytdlp: app.show_update_banner(
                        f"yt-dlp {v} is available. Installer builds get it with "
                        "a FlowSnip release.",
                        "Releases",
                        lambda: webbrowser.open(updater.FLOWSNIP_RELEASES_URL),
                    ),
                )
        elif new_ytdlp:
            _ytdlp_ver: str = new_ytdlp  # narrow str | None → str for mypy

            def _on_update_click(v: str = _ytdlp_ver) -> None:
                app.show_update_banner(
                    f"Updating yt-dlp to {v}…", "Please wait", lambda: None
                )
                threading.Thread(
                    target=_apply_ytdlp_update,
                    args=(app, v),
                    daemon=True,
                ).start()

            app.root.after(
                0,
                lambda v=new_ytdlp: app.show_update_banner(
                    f"yt-dlp {v} is available.",
                    "Update now",
                    lambda: _on_update_click(v),
                ),
            )

    config.updates.last_checked = datetime.now(tz=timezone.utc)
    config.save_to_file(config_path)


def main() -> int:
    """Main entry point for the application."""
    try:
        parser = create_arg_parser()
        args = parser.parse_args()

        config_path = args.config if args.config else get_default_config_path()
        config = Config.load_from_file(config_path)
        config.update_from_args(args)

        if getattr(args, "no_gui", False):
            print("Command-line mode is not implemented yet.")
            return 1

        gui_class = _get_gui_class()
        app = gui_class(config)

        if config.updates.check_flowsnip or config.updates.check_ytdlp:
            app.root.after(
                0,
                lambda: threading.Thread(
                    target=_run_update_checks,
                    args=(app, config, config_path),
                    daemon=True,
                ).start(),
            )

        app.run()
        return 0

    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
        return 1
    except Exception as e:
        print(f"Error starting application: {e}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
