"""
Main entry point for FlowSnip application.

This module handles command-line argument parsing, configuration loading,
and application startup.
"""

import sys

from flowsnip.config import Config, create_arg_parser, get_default_config_path
from flowsnip.gui import FlowSnipGUI


def main():
    """Main entry point for the application."""
    try:
        # Parse command line arguments
        parser = create_arg_parser()
        args = parser.parse_args()

        # Load configuration
        config_path = args.config if args.config else get_default_config_path()
        config = Config.load_from_file(config_path)

        # Update config with command line arguments
        config.update_from_args(args)

        # Check for no-gui mode (not implemented yet)
        if getattr(args, "no_gui", False):
            print("Command-line mode is not implemented yet.")
            return 1

        # Start GUI application
        app = FlowSnipGUI(config)
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
