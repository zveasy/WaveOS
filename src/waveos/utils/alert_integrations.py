from __future__ import annotations

from typing import Dict
import smtplib
from email.message import EmailMessage

from waveos.utils.alerts import send_webhook

try:
    import boto3 as _boto3
except Exception:
    _boto3 = None


def send_slack(webhook_url: str, message: Dict[str, str]) -> None:
    payload = {"text": f"Wave OS alert: {message}"}
    send_webhook(webhook_url, payload, retries=1)


def send_email(recipient: str, subject: str, body: str, provider: str = "smtp", settings: Dict | None = None) -> None:
    settings = settings or {}
    if provider == "ses":
        return send_email_ses(recipient, subject, body, settings)
    return send_email_smtp(recipient, subject, body, settings)


def send_email_smtp(recipient: str, subject: str, body: str, settings: Dict) -> None:
    host = settings.get("smtp_host")
    port = settings.get("smtp_port", 587)
    user = settings.get("smtp_user")
    password = settings.get("smtp_password")
    sender = settings.get("smtp_from") or user
    if not host or not sender:
        return None
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)


def send_email_ses(recipient: str, subject: str, body: str, settings: Dict) -> None:
    if _boto3 is None:
        return None
    region = settings.get("ses_region")
    sender = settings.get("ses_from")
    if not region or not sender:
        return None
    client = _boto3.client("ses", region_name=region)
    client.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
    )
