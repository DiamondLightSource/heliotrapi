import requests

from heliotrapi import logger

emojis = {
    "failure": ":x:",
    "success": ":white_check_mark:",
    "analysis": ":gear:",
}


def send_slack_message(message: str, webhook_url: str):
    payload = {"message": message}
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logger.info("Message sent to Slack")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message to Slack: {e} at URL: {webhook_url}")


def send_slack_failure(message: str, webhook_url: str):

    full_message = (
        f"{emojis['analysis']} {emojis['failure']} Analysis Failed: {message}"
    )
    send_slack_message(full_message, webhook_url)
