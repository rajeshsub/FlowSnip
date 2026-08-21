# FlowSnip

[![CI](https://github.com/rajeshsub/FlowSnip/actions/workflows/ci.yml/badge.svg)](https://github.com/rajeshsub/FlowSnip/actions/workflows/ci.yml)

FlowSnip is a GUI wrapper for [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## ⚠️ Legal Disclaimer

**FlowSnip is a GUI wrapper around yt-dlp. In other words, it's only just an user interface that calls out to yt-dlp! By using this tool, you acknowledge that you shall ONLY use it for accessing content that you have a legal right to access.** Users are solely responsible for ensuring their use complies with all applicable laws and the terms of service of content platforms.

**Users assume all legal risk** associated with downloading, storing, or using any content from any platform using this tool. See [DISCLAIMER.md](DISCLAIMER.md) for full details.

## Screenshot

![FlowSnip GUI - Main Interface](assets/screenshot.png)

*FlowSnip's modern CustomTkinter interface with dark theme support*

## Features

### Core Functionality
- **Modern GUI** - Beautiful CustomTkinter interface with dark/light themes
- **Download Manager** - Complete parallel download engine with queue management
- **Configuration System** - Full Pydantic-based config with CLI overrides
- **Real-time Progress** - Live progress tracking with speed, ETA, and status

### Download Features
- **Parallel Processing** - Configurable concurrent downloads (1-10 simultaneous)
- **Video Quality Selection** - Easy selection: 360p, 480p, 720p, 1080p, 1440p, 4K
- **Audio-Only Downloads** - MP3 extraction with quality options (96-320 kbps)
- **Queue Management** - Add, pause, resume, cancel, retry downloads
- **Batch Processing** - Multiple URLs via copy-paste (newline separated)

### Configuration & Persistence
- **Auto-save Settings** - Window size and preferences persisted to config file
- **Configuration Files** - Import/export JSON configurations
- **Command Line Override** - Full CLI support for scripting

### Updates
- **Auto-update Checks** - Checks for new FlowSnip releases and yt-dlp updates on startup
- **In-app Banner** - Non-intrusive notification with one-click update or dismiss
- **Configurable Frequency** - Every launch, daily, weekly, or never; individually toggleable per component

### Legal Acknowledgment
On startup, FlowSnip displays a legal disclaimer dialog that users must acknowledge. The dialog presents the key terms of responsibility and requires users to agree to proceed. If a user declines to agree, the application will exit gracefully. This ensures all users are aware of their legal obligations before using the tool.

## Installation

Pre-built installers are attached to every [GitHub Release](https://github.com/rajeshsub/FlowSnip/releases). Download the one for your platform — no Python or other prerequisites needed.

| Platform | File |
|---|---|
| Windows | `FlowSnip-x.y.z-windows-setup.exe` |
| macOS (Apple Silicon + Intel via Rosetta 2) | `FlowSnip-x.y.z-macos-arm64.dmg` |
| Linux | `FlowSnip-x.y.z-linux.AppImage` |

### ⚠️ Unsigned builds — first-launch warnings

Installers are currently unsigned. Your OS will warn you on first launch.

**Windows (SmartScreen):**
> "Windows protected your PC"

Click **More info → Run anyway**.

**macOS (Gatekeeper):**
> "FlowSnip cannot be opened because the developer cannot be verified"

Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the FlowSnip entry. Alternatively, right-click the `.app` in Finder and choose **Open**.

---

## Getting Started

### Prerequisites
- Python 3.11 or higher
- Git
- **Tk runtime for the GUI** — Required to launch the desktop interface. Python package dependencies install fine with `uv`, but Linux still needs the system Tk package:
  - Fedora/RHEL: `sudo dnf install python3-tkinter`
  - Debian/Ubuntu: `sudo apt install python3-tk`
- **Node.js** *(optional)* — Required only for bypassing yt-dlp's n-challenge rate-limiting on some sites (e.g. YouTube throttling). Install from [nodejs.org](https://nodejs.org) or via your system package manager. If Node.js is installed to a non-standard location, set `FLOWSNIP_NODE_PATH=/path/to/node` before launching.

### Quick Start (Recommended)

For new developers, use the bootstrap target to set up your environment:

```bash
# Clone the repository
git clone git@github.com:rajeshsub/FlowSnip.git
cd FlowSnip

# Bootstrap the development environment
make bootstrap

# Run the application
uv run python -m flowsnip.main
```

### Using UV Directly

If you don't have `make` installed:

```bash
# Clone the repository
git clone git@github.com:rajeshsub/FlowSnip.git
cd FlowSnip

# Install UV (if not already installed)
pip install uv

# Sync dependencies
uv sync

# Run the application
uv run python -m flowsnip.main

# Run tests
uv run pytest --cov=flowsnip

# Lint and format code
uv run ruff check --fix flowsnip tests
uv run ruff format flowsnip tests
```

### Pre-commit hooks

`make bootstrap` (or `uv run pre-commit install`) wires up git hooks automatically:

- **On `git commit`**: ruff (lint + format check), mypy, and the fast test suite (`pytest -m "not slow"`, no coverage gate).
- **On `git push`**: the same lint/type checks plus the *full* test suite, including the slower real-threading queue-manager tests (`@pytest.mark.slow`), with the 100% coverage gate enforced — matching what CI runs.

Run the full hook chain manually with `uv run pre-commit run --all-files` (commit stage) or `uv run pre-commit run --all-files --hook-stage pre-push` (push stage).

### Legacy: Using pip

```bash
# Clone the repository
git clone git@github.com:rajeshsub/FlowSnip.git
cd FlowSnip

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m flowsnip.main
```

## Configuration

```bash
# Test different configurations
python -m flowsnip.main --download-dir ~/Videos
python -m flowsnip.main --quality "best[height<=720]"
python -m flowsnip.main --audio-only --audio-quality 320
python -m flowsnip.main --max-parallel 5 --theme light
```

### Environment Variables

| Variable | Description |
|---|---|
| `FLOWSNIP_NODE_PATH` | Full path to the `node` executable (e.g. `/usr/local/bin/node` or `C:\nvm\node.exe`). Used when Node.js is installed to a non-standard location. If not set, FlowSnip searches `PATH` then common install locations automatically. |

### Code Quality Management
```bash
# Lint and auto-fix
uv run ruff check --fix flowsnip tests

# Format code
uv run ruff format flowsnip tests
```

### Automated tests with Pytest
```bash
# Run tests
pytest

# Run with coverage
pytest --cov=flowsnip
```

## Architecture

```
FlowSnip/
├── .github/
│   └── workflows/
│       └── release.yml         # CI/CD release pipeline (triggered on v*.*.* tags)
├── flowsnip/                   # Main package
│   ├── __init__.py             # Package initialization
│   ├── config.py               # Configuration management (Pydantic models)
│   ├── download_manager.py     # Download queue processing
│   ├── gui.py                  # GUI interface (CustomTkinter)
│   ├── main.py                 # Application entry point
│   └── updater.py              # Auto-update logic (FlowSnip + yt-dlp)
├── installer/                  # Packaging & distribution
│   ├── FlowSnip.spec           # PyInstaller spec (all platforms)
│   ├── pre_build.py            # Converts icon.png → .ico / .icns
│   ├── macos/
│   │   └── create_dmg.sh       # macOS DMG packaging script
│   └── windows/
│       └── FlowSnip.nsi        # NSIS wizard installer script
├── assets/                     # Static assets
│   ├── icon.png                # App icon (source)
│   ├── icon.ico                # App icon (Windows)
│   ├── icon.icns               # App icon (macOS)
│   └── screenshot.png          # GUI screenshot
├── docs/                       # Documentation
│   └── agents/                 # Agent skill configuration
├── tests/                      # Test suite
├── Makefile                    # Developer workflow targets
├── pyproject.toml              # Project configuration
├── DISCLAIMER.md               # Legal disclaimer
└── README.md                   # This file
```

## Code Signing Policy

Windows release builds are code signed using a free code signing certificate provided by [SignPath.io](https://about.signpath.io/), courtesy of the [SignPath Foundation](https://signpath.org/) open source program.

- **Authors**: Rajesh Subramanian ([@rajeshsub](https://github.com/rajeshsub))
- **Reviewers**: Rajesh Subramanian ([@rajeshsub](https://github.com/rajeshsub))
- **Approvers**: Rajesh Subramanian ([@rajeshsub](https://github.com/rajeshsub))

Privacy policy: FlowSnip does not transfer any personal data to SignPath as part of the signing process.

## Contributing

Contributions welcome! :-)

## License

MIT License - see LICENSE file for details.
