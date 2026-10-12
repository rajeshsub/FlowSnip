"""
Local PO token server for yt downloads (ADR 0004).

yt withholds most adaptive streams from web clients unless each request
carries a GVS PO token minted by Google's BotGuard script. The bundled bgutil
server mints them in Node.js; its yt-dlp plugin fetches one per video from the
URL this module hands out.
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

MIN_NODE_MAJOR = 22
SERVER_DIR_NAME = "bgutil-server"
_HOST = "127.0.0.1"
_STOP_TIMEOUT = 5.0
_VERSION_TIMEOUT = 10.0
_PING_INTERVAL = 0.25

# Loopback only: a proxy from the environment must never see these requests.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def server_dir() -> Path:
    """Where the built server lives: the bundle root when frozen, else vendor/."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / SERVER_DIR_NAME
    return Path(__file__).resolve().parent.parent / "vendor" / SERVER_DIR_NAME


def _free_port() -> int:
    """A loopback port nothing is listening on right now."""
    with socket.socket() as sock:
        sock.bind((_HOST, 0))
        return int(sock.getsockname()[1])


def _ping(base_url: str) -> bool:
    """True once the server answers its health check."""
    try:
        with _OPENER.open(f"{base_url}/ping", timeout=1) as response:
            return bool(response.status == 200)
    except OSError:
        return False


def _child_options() -> dict[str, Any]:
    """Popen/run keyword arguments for launching the system's Node.js.

    A frozen build points the library search path at its own bundled
    libraries, which break the system Node (an older libstdc++ on Linux), so
    the user's original path is restored, as yt-dlp does for its own children.
    On Windows the console window is hidden.
    """
    env = os.environ.copy()
    if hasattr(sys, "_MEIPASS"):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            original = env.get(f"{key}_ORIG")
            if original is None:
                env.pop(key, None)
            else:
                env[key] = original
    options: dict[str, Any] = {"env": env}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options


def _node_version(node: str) -> tuple[int | None, str]:
    """Major version and raw version string of a Node.js executable."""
    try:
        result = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
            **_child_options(),
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    version = result.stdout.strip()
    try:
        return int(version.lstrip("v").split(".")[0]), version
    except ValueError:
        return None, version


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Stop a server process, killing it if it ignores the request."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class PotServer:
    """Starts the bgutil server on first use and keeps it for the session.

    Failures that cannot fix themselves within a session (no Node, old Node,
    missing server files, a server that never comes up) are remembered, so a
    download never waits on them twice. A server that crashed after starting
    is relaunched.
    """

    def __init__(
        self,
        node_path: Callable[[], str | None],
        directory: Path | None = None,
        *,
        startup_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._node_path = node_path
        self.directory = directory if directory is not None else server_dir()
        self._startup_timeout = startup_timeout
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._url: str | None = None
        self._exit_hook_registered = False
        self.unavailable_reason: str | None = None

    def base_url(self) -> str | None:
        """URL of a running server, launching it if needed; None if unavailable."""
        with self._lock:
            if self.unavailable_reason is not None:
                return None
            if self._process is not None and self._process.poll() is None:
                return self._url
            self._process = None
            self._url = None
            self.unavailable_reason = self._launch()
            return self._url

    def stop(self) -> None:
        """Stop the server if it is running."""
        with self._lock:
            process, self._process, self._url = self._process, None, None
        if process is not None:
            _terminate(process)

    def _launch(self) -> str | None:
        """Start the server; return why it is unavailable, or None on success."""
        node = self._node_path()
        if not node:
            return f"Node.js {MIN_NODE_MAJOR} or newer was not found"
        major, version = _node_version(node)
        if major is None or major < MIN_NODE_MAJOR:
            found = f" (found {version})" if version else ""
            return f"Node.js {MIN_NODE_MAJOR} or newer is required{found}"
        script = self.directory / "build" / "main.js"
        if not script.is_file():
            return f"the PO token server is not installed ({self.directory})"

        port = _free_port()
        url = f"http://{_HOST}:{port}"
        try:
            process = subprocess.Popen(
                [node, str(script), "-H", _HOST, "-p", str(port)],
                cwd=str(self.directory),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_child_options(),
            )
        except OSError as e:
            return f"the PO token server could not be launched: {e}"
        if not self._exit_hook_registered:
            atexit.register(self.stop)
            self._exit_hook_registered = True

        deadline = self._clock() + self._startup_timeout
        while process.poll() is None and self._clock() < deadline:
            if _ping(url):
                self._process, self._url = process, url
                return None
            self._sleep(_PING_INTERVAL)
        _terminate(process)
        return "the PO token server did not start"
