"""
Build the bgutil PO token server into vendor/bgutil-server (ADR 0004).

Run from the repo root (make bootstrap and the release jobs do this):
    python installer/build_pot_server.py [--audit]

--audit fails the build on high or critical npm advisories in the server's
production dependencies (release and scheduled audit jobs pass it).

Needs git, and Node.js 22+ with npm on PATH. The result is specific to the
OS and CPU it was built on (the canvas dependency is a native addon), so each
release job builds its own. Skips the build when the pinned commit is already
in place.

Keep BGUTIL_VERSION equal to the bgutil-ytdlp-pot-provider pin in
pyproject.toml: the plugin and the server are released together.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BGUTIL_REPO = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
BGUTIL_VERSION = "2.0.2"
BGUTIL_COMMIT = "26475e9d3665b972c4aeb83b4dbaafcf64b88438"

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "vendor" / "bgutil-server"
STAMP = TARGET / ".commit"


def run(*args: str, cwd: Path) -> str:
    """Run a command, echoing it, and return its stdout."""
    print(f"  $ {' '.join(args)}")
    tool = shutil.which(args[0])
    if tool is None:
        sys.exit(f"{args[0]} not found on PATH")
    result = subprocess.run(
        [tool, *args[1:]], cwd=cwd, check=True, stdout=subprocess.PIPE, text=True
    )
    return result.stdout.strip()


def build(workdir: Path, audit: bool) -> None:
    """Clone the pinned commit and leave a production build in TARGET."""
    checkout = workdir / "bgutil"
    run(
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--branch",
        BGUTIL_VERSION,
        BGUTIL_REPO,
        str(checkout),
        cwd=workdir,
    )
    commit = run("git", "rev-parse", "HEAD", cwd=checkout)
    if commit != BGUTIL_COMMIT:
        sys.exit(
            f"bgutil tag {BGUTIL_VERSION} points at {commit}, "
            f"expected {BGUTIL_COMMIT}; refusing to build"
        )

    server = checkout / "server"
    run("npm", "ci", "--no-audit", "--no-fund", cwd=server)
    if audit:
        run("npm", "audit", "--omit=dev", "--audit-level=high", cwd=server)
    run("npx", "tsc", cwd=server)
    run("npm", "prune", "--omit=dev", "--no-audit", "--no-fund", cwd=server)

    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    # node_modules/.bin holds symlinked CLI shims the server never runs, and
    # symlinks don't survive every installer format.
    shutil.rmtree(server / "node_modules" / ".bin", ignore_errors=True)
    for name in ("build", "node_modules"):
        shutil.copytree(server / name, TARGET / name)
    shutil.copy2(server / "package.json", TARGET / "package.json")
    shutil.copy2(checkout / "LICENSE", TARGET / "LICENSE")
    STAMP.write_text(BGUTIL_COMMIT + "\n")


if __name__ == "__main__":
    audit = "--audit" in sys.argv[1:]
    if not audit and STAMP.is_file() and STAMP.read_text().strip() == BGUTIL_COMMIT:
        print(f"bgutil server {BGUTIL_VERSION} already built in {TARGET}")
        sys.exit(0)
    print(f"Building bgutil server {BGUTIL_VERSION} …")
    with tempfile.TemporaryDirectory() as workdir:
        build(Path(workdir), audit)
    print(f"  wrote {TARGET}")
