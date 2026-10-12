"""Tests for flowsnip/pot_server.py - the bundled PO token server (ADR 0004)."""

import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flowsnip import pot_server
from flowsnip.pot_server import PotServer, server_dir

NODE = "/usr/bin/node"


@pytest.fixture
def server_home(tmp_path):
    """A directory laid out like a built bgutil server."""
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "main.js").write_text("")
    return tmp_path


class FakeClock:
    """Injectable clock: sleeping advances time instead of waiting."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _node_version(version="v22.23.1"):
    return subprocess.CompletedProcess([NODE, "--version"], 0, f"{version}\n", "")


def _process(running=True):
    proc = MagicMock()
    proc.poll.return_value = None if running else 1
    return proc


def _server(home, node=NODE, **kwargs):
    clock = kwargs.pop("clock", FakeClock())
    return PotServer(
        lambda: node,
        home,
        startup_timeout=kwargs.pop("startup_timeout", 5.0),
        clock=clock,
        sleep=clock.sleep,
    )


# ---------------------------------------------------------------------------
# Unavailable: no URL, a reason for the activity log
# ---------------------------------------------------------------------------


def test_no_node_runtime_gives_no_url(server_home):
    server = _server(server_home, node=None)
    with patch("subprocess.Popen") as popen:
        assert server.base_url() is None
    popen.assert_not_called()
    assert "Node.js 22" in server.unavailable_reason


def test_node_older_than_22_gives_no_url(server_home):
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version("v20.11.0")),
        patch("subprocess.Popen") as popen,
    ):
        assert server.base_url() is None
    popen.assert_not_called()
    assert "v20.11.0" in server.unavailable_reason
    assert "Node.js 22" in server.unavailable_reason


@pytest.mark.parametrize(
    "outcome",
    [
        OSError("not executable"),
        subprocess.TimeoutExpired(NODE, 10),
        _node_version("not a version"),
    ],
)
def test_unreadable_node_version_gives_no_url(server_home, outcome):
    server = _server(server_home)
    kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {}
    with (
        patch("subprocess.run", return_value=outcome, **kwargs),
        patch("subprocess.Popen") as popen,
    ):
        assert server.base_url() is None
    popen.assert_not_called()
    assert "Node.js 22" in server.unavailable_reason


def test_missing_server_files_give_no_url(tmp_path):
    server = _server(tmp_path)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen") as popen,
    ):
        assert server.base_url() is None
    popen.assert_not_called()
    assert "not installed" in server.unavailable_reason


def test_permanent_failure_is_not_probed_again(server_home):
    server = _server(server_home)
    with patch("subprocess.run", return_value=_node_version("v18.0.0")) as run:
        assert server.base_url() is None
        assert server.base_url() is None
    run.assert_called_once()


# ---------------------------------------------------------------------------
# Launching and reusing the server
# ---------------------------------------------------------------------------


def test_launches_on_loopback_and_returns_url_once_ping_answers(server_home):
    server = _server(server_home)
    pings = iter([False, False, True])
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", side_effect=lambda url: next(pings)),
        patch.object(pot_server.atexit, "register"),
    ):
        assert server.base_url() == "http://127.0.0.1:48123"
    args = popen.call_args.args[0]
    assert args == [
        NODE,
        str(server_home / "build" / "main.js"),
        "-H",
        "127.0.0.1",
        "-p",
        "48123",
    ]
    assert popen.call_args.kwargs["cwd"] == str(server_home)
    assert server.unavailable_reason is None


def test_second_call_reuses_running_server(server_home):
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        first = server.base_url()
        second = server.base_url()
    assert first == second == "http://127.0.0.1:48123"
    popen.assert_called_once()


def test_concurrent_first_calls_launch_once(server_home):
    server = _server(server_home)
    results = []
    gate = threading.Barrier(5)

    def worker():
        gate.wait()
        results.append(server.base_url())

    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert results == ["http://127.0.0.1:48123"] * 5
    popen.assert_called_once()


def test_crashed_server_is_relaunched(server_home):
    server = _server(server_home)
    first, second = _process(), _process()
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", side_effect=[first, second]) as popen,
        patch.object(pot_server, "_free_port", side_effect=[48123, 48124]),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        assert server.base_url() == "http://127.0.0.1:48123"
        first.poll.return_value = 1  # exited
        assert server.base_url() == "http://127.0.0.1:48124"
    assert popen.call_count == 2


def test_server_that_never_answers_is_stopped_and_not_retried(server_home):
    server = _server(server_home, startup_timeout=3.0)
    proc = _process()
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=proc) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=False),
        patch.object(pot_server.atexit, "register"),
    ):
        assert server.base_url() is None
        assert server.base_url() is None
    proc.terminate.assert_called_once()
    popen.assert_called_once()
    assert "did not start" in server.unavailable_reason


def test_server_that_exits_during_startup_is_not_retried(server_home):
    server = _server(server_home)
    proc = _process(running=False)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=proc) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=False) as ping,
        patch.object(pot_server.atexit, "register"),
    ):
        assert server.base_url() is None
        assert server.base_url() is None
    popen.assert_called_once()
    ping.assert_not_called()
    assert "did not start" in server.unavailable_reason


def test_launch_error_gives_no_url(server_home):
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", side_effect=OSError("exec format error")),
        patch.object(pot_server, "_free_port", return_value=48123),
    ):
        assert server.base_url() is None
    assert "exec format error" in server.unavailable_reason


def test_windows_launch_hides_the_console(server_home):
    server = _server(server_home)
    with (
        patch.object(pot_server.sys, "platform", "win32"),
        patch.object(
            pot_server.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True
        ),
        patch("subprocess.run", return_value=_node_version()) as run,
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        server.base_url()
    assert popen.call_args.kwargs["creationflags"] == 0x08000000
    assert run.call_args.kwargs["creationflags"] == 0x08000000


def test_frozen_launch_gives_node_the_system_library_path(server_home, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(server_home), raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/lib")
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/bundle/_internal")
    monkeypatch.delenv("DYLD_LIBRARY_PATH_ORIG", raising=False)
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()) as run,
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        server.base_url()
    for call in (run.call_args, popen.call_args):
        env = call.kwargs["env"]
        assert env["LD_LIBRARY_PATH"] == "/opt/lib"
        assert "DYLD_LIBRARY_PATH" not in env
        assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_source_launch_passes_the_environment_through(server_home, monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/lib")
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=_process()) as popen,
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        server.base_url()
    env = popen.call_args.kwargs["env"]
    assert env["LD_LIBRARY_PATH"] == "/opt/lib"
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in env


def test_first_launch_registers_stop_at_exit(server_home):
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", side_effect=[_process(), _process()]),
        patch.object(pot_server, "_free_port", side_effect=[48123, 48124]),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register") as register,
    ):
        server.base_url()
        server.stop()
        server.base_url()
    register.assert_called_once_with(server.stop)


# ---------------------------------------------------------------------------
# Stopping
# ---------------------------------------------------------------------------


def _running_server(server_home, proc):
    server = _server(server_home)
    with (
        patch("subprocess.run", return_value=_node_version()),
        patch("subprocess.Popen", return_value=proc),
        patch.object(pot_server, "_free_port", return_value=48123),
        patch.object(pot_server, "_ping", return_value=True),
        patch.object(pot_server.atexit, "register"),
    ):
        server.base_url()
    return server


def test_stop_terminates_the_server(server_home):
    proc = _process()
    server = _running_server(server_home, proc)
    server.stop()
    proc.terminate.assert_called_once()
    proc.wait.assert_called_once()
    proc.kill.assert_not_called()


def test_stop_kills_a_server_that_ignores_terminate(server_home):
    proc = _process()
    proc.wait.side_effect = [subprocess.TimeoutExpired(NODE, 5), 0]
    server = _running_server(server_home, proc)
    server.stop()
    proc.kill.assert_called_once()


def test_stop_skips_a_server_that_already_exited(server_home):
    proc = _process()
    server = _running_server(server_home, proc)
    proc.poll.return_value = 0
    server.stop()
    proc.terminate.assert_not_called()


def test_stop_without_a_server_is_a_no_op(server_home):
    _server(server_home).stop()


# ---------------------------------------------------------------------------
# Locating the server and talking to it
# ---------------------------------------------------------------------------


def test_server_dir_from_source_is_vendor_dir():
    expected = Path(pot_server.__file__).resolve().parent.parent / "vendor"
    assert server_dir() == expected / "bgutil-server"


def test_server_dir_when_frozen_is_bundle_root(tmp_path):
    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "_MEIPASS", str(tmp_path), create=True),
    ):
        assert server_dir() == tmp_path / "bgutil-server"


def test_default_directory_is_server_dir():
    assert PotServer(lambda: None).directory == server_dir()


def test_free_port_is_bindable():
    import socket

    port = pot_server._free_port()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def test_ping_true_when_server_answers():
    response = MagicMock()
    response.__enter__.return_value.status = 200
    opener = MagicMock()
    opener.open.return_value = response
    with patch.object(pot_server, "_OPENER", opener):
        assert pot_server._ping("http://127.0.0.1:48123") is True
    opener.open.assert_called_once_with("http://127.0.0.1:48123/ping", timeout=1)


def test_ping_false_when_connection_refused():
    opener = MagicMock()
    opener.open.side_effect = OSError("refused")
    with patch.object(pot_server, "_OPENER", opener):
        assert pot_server._ping("http://127.0.0.1:48123") is False


def test_ping_reaches_loopback_despite_a_proxy_in_the_environment(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/ping" else 404)
            self.end_headers()

        def log_message(self, *args):
            pass

    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("no_proxy", "")
    with HTTPServer(("127.0.0.1", 0), Handler) as httpd:
        thread = threading.Thread(target=httpd.handle_request)
        thread.start()
        assert pot_server._ping(f"http://127.0.0.1:{httpd.server_port}") is True
        thread.join()
