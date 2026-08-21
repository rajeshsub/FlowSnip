Status: Accepted

# 0001. Packaging and distribution strategy

## Context

FlowSnip is a Python desktop GUI application (CustomTkinter) wrapping yt-dlp. Its
target users are non-technical end users on Windows, macOS, and Linux who cannot
be expected to have Python or `uv` installed, or to run the app from source.
The project needed a way to produce a bundled, double-clickable artifact on each
of the three desktop platforms, plus a platform-idiomatic installer wrapped
around that artifact, built and published from a single CI release pipeline
(`.github/workflows/release.yml`).

## Options

- **PyInstaller** (chosen): bundles the interpreter and all dependencies into a
  single-directory or single-file executable per platform. Mature, single extra
  dependency, works with CustomTkinter/Pillow/yt-dlp without custom build
  plugins, and integrates cleanly with a `.spec` file that can be checked into
  the repo (`installer/FlowSnip.spec`). Downside: produces a large output
  directory, doesn't fetch runtime binaries like ffmpeg, and needs an
  icon-conversion step for platform-native icon formats.
- **cx_Freeze**: similar bundling approach to PyInstaller, but smaller community
  around CustomTkinter/Tkinter apps, and historically weaker macOS `.app`
  bundle support. No clear advantage over PyInstaller for this stack.
- **Nuitka**: compiles Python to C, which can produce faster and sometimes
  smaller binaries, but has a heavier build pipeline, longer CI build times,
  and more platform-specific compiler toolchain requirements (MSVC on Windows,
  a full C toolchain on macOS/Linux) that would add CI complexity for no
  functional benefit to a GUI download tool.
- **briefcase/BeeWare**: opinionated cross-platform packaging framework with
  its own project layout and app model. Would have required restructuring the
  existing `flowsnip` package layout to fit BeeWare's conventions, a rewrite
  cost not justified given PyInstaller already works with the existing layout.
- **Native package managers only (winget/homebrew/apt), no bundled interpreter**:
  would push the burden of having a compatible Python runtime onto the end
  user, and doesn't solve the "double-click and run" requirement for a
  non-technical end user distribution channel. Rejected outright.

## Decision

Use PyInstaller to produce a bundled executable/app per platform from
`installer/FlowSnip.spec`, driven by `installer/pre_build.py` to convert
`assets/icon.png` into the platform-native icon formats (`icon.ico` for
Windows, `icon.icns` for macOS) that PyInstaller's `EXE`/`BUNDLE` steps
consume. On top of the PyInstaller output, wrap a platform-idiomatic installer:

- Windows: an NSIS wizard installer (`installer/windows/FlowSnip.nsi`) that
  installs to Program Files, registers Add/Remove Programs entries, and
  creates Start Menu / optional Desktop shortcuts.
- macOS: a DMG built by `installer/macos/create_dmg.sh`, which stages
  `FlowSnip.app` next to an `/Applications` symlink and packages it with
  `hdiutil`.
- Linux: a self-integrating AppImage, built inline inside the `build-linux`
  job of `.github/workflows/release.yml` (there is no separate
  `installer/linux/` script; the AppDir structure, `.desktop` entry, and
  `AppRun` launcher are generated directly in the workflow step).

ffmpeg and ffprobe binaries are downloaded per-platform in each CI build job
(from BtbN's Windows builds, evermeet.cx for macOS, and John Van Sickle's
static Linux builds) into `ffmpeg_bin/`, and `FlowSnip.spec` picks them up from
that directory and bundles them into the PyInstaller output if present, since
PyInstaller itself has no mechanism to fetch runtime third-party binaries.

## Consequences

- The release pipeline needs three separate OS runners (`windows-latest`,
  `macos-latest`, `ubuntu-latest`) in `build-windows`, `build-macos-arm64`, and
  `build-linux` jobs, each running its own PyInstaller build rather than
  cross-compiling from one host.
- ffmpeg/ffprobe must be fetched and vendored separately in each platform job;
  a change to the ffmpeg source URL or version pin has to be made in three
  places.
- Icon assets require the `installer/pre_build.py` conversion step to run
  before every PyInstaller build, so it is a required step in all three build
  jobs, not an optional developer convenience.
- The macOS build currently produces an unsigned, non-notarized DMG; the
  signing gap is deliberate and tracked as a separate follow-up, not an
  oversight of this decision.
- The Linux AppImage has no code-signing concept at all (AppImages are
  typically distributed unsigned, verified by checksum), so no signing
  question arises for that platform under this decision.
- Only Windows currently has code-signing wired into the pipeline; see ADR
  0002 for that decision.
