from __future__ import annotations

from typing import Dict

from waveos.utils.alerts import send_webhook


def send_slack(webhook_url: str, message: Dict[str, str]) -> None:
    payload = {"text": f"Wave OS alert: {message}"}
    send_webhook(webhook_url, payload, retries=1)


def send_email(recipient: str, subject: str, body: str) -> None:
    # Placeholder for real email delivery (SMTP/API)
    return None
