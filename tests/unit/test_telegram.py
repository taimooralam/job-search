"""
Unit tests for src/common/telegram.py

Tests Telegram notification module with mocked HTTP calls.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.common.telegram import (
    send_telegram,
    notify_cron_complete,
    notify_pipeline_complete,
    notify_pipeline_failed,
)


class TestSendTelegram:
    """Tests for the core send_telegram function."""

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "12345"})
    @patch("src.common.telegram.requests.post")
    def test_sends_message_successfully(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = send_telegram("Hello")
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "test-token" in call_kwargs[0][0]
        assert call_kwargs[1]["json"]["chat_id"] == "12345"
        assert call_kwargs[1]["json"]["text"] == "Hello"

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_false_when_not_configured(self):
        result = send_telegram("Hello")
        assert result is False

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"})
    @patch("src.common.telegram.requests.post")
    def test_returns_false_on_api_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
        result = send_telegram("Hello")
        assert result is False

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"})
    @patch("src.common.telegram.requests.post", side_effect=Exception("Network error"))
    def test_returns_false_on_exception(self, mock_post):
        result = send_telegram("Hello")
        assert result is False


class TestNotifyCronComplete:
    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_formats_success_message(self, mock_send):
        result = notify_cron_complete(
            searched=500, scored=50, new_after_dedup=30,
            inserted=10, queued=10, failed=0,
        )
        assert result is True
        msg = mock_send.call_args[0][0]
        assert "Scout Cron Complete" in msg
        assert "500" in msg
        assert "10" in msg

    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_includes_failure_count(self, mock_send):
        notify_cron_complete(
            searched=100, scored=10, new_after_dedup=5,
            inserted=5, queued=2, failed=3,
        )
        msg = mock_send.call_args[0][0]
        assert "3" in msg
        assert "failures" in msg.lower() or "failure" in msg.lower()


class TestNotifyPipelineComplete:
    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_formats_complete_message(self, mock_send):
        result = notify_pipeline_complete(
            job_id="abc123", company="Acme", role="AI Engineer",
            duration_s=154.0,
        )
        assert result is True
        msg = mock_send.call_args[0][0]
        assert "Acme" in msg
        assert "AI Engineer" in msg
        assert "2m 34s" in msg

    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_short_duration_format(self, mock_send):
        notify_pipeline_complete(
            job_id="abc", company="X", role="Y", duration_s=45.0,
        )
        msg = mock_send.call_args[0][0]
        assert "45s" in msg


class TestNotifyPipelineFailed:
    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_formats_failure_message(self, mock_send):
        result = notify_pipeline_failed(
            job_id="abc123", company="Acme", role="AI Engineer",
            error="Connection timeout", run_id="run_xyz",
        )
        assert result is True
        msg = mock_send.call_args[0][0]
        assert "Acme" in msg
        assert "Connection timeout" in msg
        assert "run_xyz" in msg[:50] or "run_xyz" in msg

    @patch("src.common.telegram.send_telegram", return_value=True)
    def test_truncates_long_error(self, mock_send):
        long_error = "x" * 300
        notify_pipeline_failed(
            job_id="abc", company="X", role="Y", error=long_error,
        )
        msg = mock_send.call_args[0][0]
        assert "..." in msg
        # Error should be truncated to ~150 chars
        assert len(long_error) > 200  # Sanity check
