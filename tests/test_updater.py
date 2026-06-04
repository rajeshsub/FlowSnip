"""Tests for flowsnip/updater.py — targets 100% line coverage."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from flowsnip import updater

# ---------------------------------------------------------------------------
# _fetch_latest_tag
# ---------------------------------------------------------------------------


def _mock_urlopen(tag_name: str):
    """Return a context-manager mock that yields a response with the given tag."""
    payload = json.dumps({"tag_name": tag_name}).encode()
    resp = MagicMock()
    resp.read.return_value = payload
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_fetch_latest_tag_success():
    with patch("flowsnip.updater.urllib.request.urlopen", return_value=_mock_urlopen("v2.0.0")):
        result = updater._fetch_latest_tag(updater._FLOWSNIP_API)
    assert result == "v2.0.0"


def test_fetch_latest_tag_network_error():
    with patch("flowsnip.updater.urllib.request.urlopen", side_effect=OSError("timeout")):
        result = updater._fetch_latest_tag(updater._FLOWSNIP_API)
    assert result is None


def test_fetch_latest_tag_malformed_json():
    resp = MagicMock()
    resp.read.return_value = b"not json {"
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    with patch("flowsnip.updater.urllib.request.urlopen", return_value=resp):
        result = updater._fetch_latest_tag(updater._YTDLP_API)
    assert result is None


def test_fetch_latest_tag_missing_key():
    resp = MagicMock()
    resp.read.return_value = json.dumps({"name": "release"}).encode()
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    with patch("flowsnip.updater.urllib.request.urlopen", return_value=resp):
        result = updater._fetch_latest_tag(updater._FLOWSNIP_API)
    assert result is None


# ---------------------------------------------------------------------------
# _is_newer
# ---------------------------------------------------------------------------


def test_is_newer_true():
    assert updater._is_newer("v1.2.0", "v1.1.0") is True


def test_is_newer_false_same():
    assert updater._is_newer("v1.1.0", "v1.1.0") is False


def test_is_newer_false_older():
    assert updater._is_newer("v1.0.0", "v1.1.0") is False


def test_is_newer_none_triggers_except():
    # None.lstrip raises AttributeError — caught by the except clause
    assert updater._is_newer(None, "1.0.0") is False


# ---------------------------------------------------------------------------
# check_flowsnip_update / check_ytdlp_update
# ---------------------------------------------------------------------------


def test_check_flowsnip_update_newer():
    with patch("flowsnip.updater._fetch_latest_tag", return_value="v9.9.9"):
        result = updater.check_flowsnip_update("0.1.0")
    assert result == "v9.9.9"


def test_check_flowsnip_update_same():
    with patch("flowsnip.updater._fetch_latest_tag", return_value="v0.1.0"):
        result = updater.check_flowsnip_update("0.1.0")
    assert result is None


def test_check_flowsnip_update_fetch_fails():
    with patch("flowsnip.updater._fetch_latest_tag", return_value=None):
        result = updater.check_flowsnip_update("0.1.0")
    assert result is None


def test_check_ytdlp_update_newer():
    with patch("flowsnip.updater._fetch_latest_tag", return_value="2026.12.01"):
        result = updater.check_ytdlp_update("2026.01.01")
    assert result == "2026.12.01"


def test_check_ytdlp_update_none():
    with patch("flowsnip.updater._fetch_latest_tag", return_value=None):
        result = updater.check_ytdlp_update("2026.01.01")
    assert result is None


# ---------------------------------------------------------------------------
# should_check
# ---------------------------------------------------------------------------


def test_should_check_never():
    assert updater.should_check(None, updater.FREQUENCY_NEVER) is False


def test_should_check_every_launch():
    assert updater.should_check(None, updater.FREQUENCY_EVERY_LAUNCH) is True


def test_should_check_last_checked_none():
    assert updater.should_check(None, updater.FREQUENCY_DAILY) is True


def test_should_check_daily_not_elapsed():
    recent = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    assert updater.should_check(recent, updater.FREQUENCY_DAILY) is False


def test_should_check_daily_elapsed():
    old = datetime.now(tz=timezone.utc) - timedelta(days=2)
    assert updater.should_check(old, updater.FREQUENCY_DAILY) is True


def test_should_check_weekly_not_elapsed():
    recent = datetime.now(tz=timezone.utc) - timedelta(days=3)
    assert updater.should_check(recent, updater.FREQUENCY_WEEKLY) is False


def test_should_check_weekly_elapsed():
    old = datetime.now(tz=timezone.utc) - timedelta(days=8)
    assert updater.should_check(old, updater.FREQUENCY_WEEKLY) is True


def test_should_check_unknown_frequency_returns_true():
    # Frequency not in _FREQUENCY_DELTAS — treated as "check now"
    assert updater.should_check(datetime.now(tz=timezone.utc), "monthly") is True


def test_should_check_naive_datetime_gets_utc():
    # last_checked with no tzinfo should be treated as UTC
    naive = datetime.utcnow() - timedelta(hours=1)
    assert naive.tzinfo is None
    result = updater.should_check(naive, updater.FREQUENCY_DAILY)
    assert result is False


# ---------------------------------------------------------------------------
# update_ytdlp
# ---------------------------------------------------------------------------


def test_update_ytdlp_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("flowsnip.updater.subprocess.run", return_value=mock_result):
        assert updater.update_ytdlp() is True


def test_update_ytdlp_failure():
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("flowsnip.updater.subprocess.run", return_value=mock_result):
        assert updater.update_ytdlp() is False


def test_update_ytdlp_exception():
    with patch("flowsnip.updater.subprocess.run", side_effect=Exception("pip not found")):
        assert updater.update_ytdlp() is False
