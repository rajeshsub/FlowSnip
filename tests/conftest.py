"""Shared fixtures for FlowSnip tests."""

import shutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from flowsnip.config import Config
from flowsnip.download_manager import DownloadItem, DownloadManager

# ---------------------------------------------------------------------------
# Stub customtkinter and tkinter BEFORE any test file imports flowsnip.gui
# or flowsnip.main (which transitively imports gui). conftest.py is always
# loaded by pytest before collecting/importing test files, so calling this
# function here ensures the stubs are in sys.modules first.
# ---------------------------------------------------------------------------


def _inject_gui_stubs():
    if "customtkinter" in sys.modules:
        return

    ctk = types.ModuleType("customtkinter")

    class _Base:
        def __init__(self, *a, **kw):
            pass

        def grid(self, **kw):
            pass

        def grid_remove(self):
            pass

        def pack(self, **kw):
            pass

        def configure(self, **kw):
            pass

        def grid_columnconfigure(self, *a, **kw):
            pass

        def grid_rowconfigure(self, *a, **kw):
            pass

        def destroy(self):
            pass

        def winfo_exists(self):
            return True

        def bind(self, *a, **kw):
            pass

        def set(self, v):
            pass

        def get(self):
            return ""

        def insert(self, *a, **kw):
            pass

        def delete(self, *a, **kw):
            pass

        def see(self, *a, **kw):
            pass

        def after(self, *a, **kw):
            pass

        def title(self, *a):
            pass

        def geometry(self, *a):
            return "1200x800+0+0"

        def minsize(self, *a):
            pass

        def mainloop(self):
            pass

        def protocol(self, *a):
            pass

        def clipboard_clear(self):
            pass

        def clipboard_append(self, *a):
            pass

        def count(self, *a):
            return 0

    class CTkFrame(_Base):
        pass

    class CTkLabel(_Base):
        pass

    class CTkButton(_Base):
        pass

    class CTkProgressBar(_Base):
        pass

    class CTkOptionMenu(_Base):
        pass

    class CTkCheckBox(_Base):
        pass

    class CTkSlider(_Base):
        pass

    class CTkScrollableFrame(_Base):
        pass

    class CTkTextbox(_Base):
        pass

    class CTk(_Base):
        pass

    class StringVar:
        def __init__(self, value=""):
            self._v = value

        def get(self):
            return self._v

        def set(self, v):
            self._v = v

    class BooleanVar:
        def __init__(self, value=False):
            self._v = value

        def get(self):
            return self._v

        def set(self, v):
            self._v = v

    class CTkFont:
        def __init__(self, *a, **kw):
            pass

    ctk.CTkFrame = CTkFrame
    ctk.CTkLabel = CTkLabel
    ctk.CTkButton = CTkButton
    ctk.CTkProgressBar = CTkProgressBar
    ctk.CTkOptionMenu = CTkOptionMenu
    ctk.CTkCheckBox = CTkCheckBox
    ctk.CTkSlider = CTkSlider
    ctk.CTkScrollableFrame = CTkScrollableFrame
    ctk.CTkTextbox = CTkTextbox
    ctk.CTk = CTk
    ctk.StringVar = StringVar
    ctk.BooleanVar = BooleanVar
    ctk.CTkFont = CTkFont
    ctk.set_appearance_mode = MagicMock()
    ctk.set_default_color_theme = MagicMock()

    tk_stub = types.ModuleType("tkinter")
    filedialog_stub = types.ModuleType("tkinter.filedialog")
    messagebox_stub = types.ModuleType("tkinter.messagebox")
    tk_stub.filedialog = filedialog_stub
    tk_stub.messagebox = messagebox_stub
    filedialog_stub.askdirectory = MagicMock(return_value="")
    filedialog_stub.asksaveasfilename = MagicMock(return_value="")
    filedialog_stub.askopenfilename = MagicMock(return_value="")
    messagebox_stub.showinfo = MagicMock()
    messagebox_stub.showwarning = MagicMock()
    messagebox_stub.showerror = MagicMock()
    messagebox_stub.askyesno = MagicMock()

    sys.modules["customtkinter"] = ctk
    sys.modules["tkinter"] = tk_stub
    sys.modules["tkinter.filedialog"] = filedialog_stub
    sys.modules["tkinter.messagebox"] = messagebox_stub


_inject_gui_stubs()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def test_config(temp_dir):
    config = Config()
    config.download.download_directory = temp_dir / "downloads"
    config.download.download_directory.mkdir(parents=True, exist_ok=True)
    config.download.max_parallel_downloads = 2
    config.download.retry_attempts = 1
    config.download.cookies_from_browser = None
    config.download.cookies_file = None
    return config


@pytest.fixture
def mock_callback():
    return MagicMock()


@pytest.fixture
def download_manager(test_config, mock_callback):
    manager = DownloadManager(test_config, mock_callback)
    yield manager
    manager.stop_downloads()


@pytest.fixture
def sample_item():
    return DownloadItem(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="Test Video"
    )
