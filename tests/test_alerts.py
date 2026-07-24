from unittest.mock import Mock, patch

import httpx

from heliotrapi.utils.slack_alerts import (
    emojis,
    send_slack_failure,
    send_slack_message,
)


@patch("heliotrapi.utils.slack_alerts.logger")
@patch("heliotrapi.utils.slack_alerts.httpx.post")
def test_send_slack_message_success(mock_post, mock_logger):
    response = Mock()
    response.raise_for_status.return_value = None
    mock_post.return_value = response

    send_slack_message("hello", "https://example.com/webhook")

    mock_post.assert_called_once_with(
        "https://example.com/webhook",
        json={"message": "hello"},
    )
    response.raise_for_status.assert_called_once()
    mock_logger.info.assert_called_once_with("Message sent to Slack")


@patch("heliotrapi.utils.slack_alerts.logger")
@patch("heliotrapi.utils.slack_alerts.httpx.post")
def test_send_slack_message_request_exception(mock_post, mock_logger):
    mock_post.side_effect = httpx.RequestError("boom")

    webhook_url = "https://example.com/webhook"

    send_slack_message("hello", webhook_url)

    mock_logger.error.assert_called_once_with(
        f"Failed to send message to Slack: boom at URL: {webhook_url}"
    )


@patch("heliotrapi.utils.slack_alerts.send_slack_message")
def test_send_slack_failure_formats_message(mock_send_slack_message):
    webhook_url = "https://example.com/webhook"
    message = "Database connection failed"

    send_slack_failure(message, webhook_url)

    expected_message = (
        f"{emojis['analysis']} {emojis['failure']} Analysis Failed: {message}"
    )

    mock_send_slack_message.assert_called_once_with(
        expected_message,
        webhook_url,
    )
