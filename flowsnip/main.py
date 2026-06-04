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

from flowsnip import __version__, updater
from flowsnip.config import Config, create_arg_parser, get_default_config_path
from flowsnip.gui import FlowSnipGUI


def _apply_ytdlp_update(app: FlowSnipGUI, new_ytdlp: str) -> None:
    """Run yt-dlp in-place upgrade and post result banner back to the GUI thread."""
    success = updater.update_ytdlp()
    msg = (
        f"yt-dlp updated to {new_ytdlp}."
        if success
        else "yt-dlp update failed — check your connection."
    )
    app.root.after(
        0,
        lambda m=msg: app.show_update_banner(m, "OK", app._dismiss_update_banner),
    )


def _run_update_checks(app: FlowSnipGUI, config: Config, config_path: Path | str) -> None:
    """Background thread: check for FlowSnip and yt-dlp updates."""
    cfg = config.updates

    if not updater.should_check(cfg.last_checked, cfg.frequency):
        return

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
        import yt_dlp

        current_ytdlp = getattr(yt_dlp, "__version__", "0")
        new_ytdlp = updater.check_ytdlp_update(current_ytdlp)
        if new_ytdlp:
            app.root.after(
                0,
                lambda v=new_ytdlp: app.show_update_banner(
                    f"yt-dlp {v} is available.",
                    "Update now",
                    lambda: threading.Thread(
                        target=_apply_ytdlp_update,
                        args=(app, v),
                        daemon=True,
                    ).start(),
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

        app = FlowSnipGUI(config)

        if config.updates.check_flowsnip or config.updates.check_ytdlp:
            threading.Thread(
                target=_run_update_checks,
                args=(app, config, config_path),
                daemon=True,
            ).start()

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
