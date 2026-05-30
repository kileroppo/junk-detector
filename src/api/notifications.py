"""Notification dispatcher - routes events to WebSocket and optional email.

Supports:
- WebSocket push (immediate, to all connected clients)
- Email notification (optional, via SMTP, disabled by default)
- Webhook POST (optional, with HMAC signature)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches notifications to WebSocket clients and optionally email/webhook."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._ws_enabled = self._config.get("websocket", True)
        self._email_config = self._config.get("email", {})
        self._email_enabled = self._email_config.get("enabled", False)

    @property
    def config(self) -> dict[str, Any]:
        """Return the notification config."""
        return self._config

    async def notify_score_completed(self, result: dict) -> None:
        """Notify clients that a scoring has completed."""
        if self._ws_enabled:
            from src.api.websocket import manager
            await manager.broadcast("score_completed", result)

        if self._email_enabled:
            score = result.get("score", "N/A")
            subject = f"[Junk Detector] Score: {score}"
            body = f"Scoring completed.\nScore: {score}\nSummary: {result.get('summary', '')}"
            self._send_email(subject, body)

    async def notify_monitor_alert(self, item: dict, score: float) -> None:
        """Notify clients of a monitor alert (content below threshold)."""
        alert_data = {
            "item": item,
            "score": score,
            "alert_type": "below_threshold",
        }

        if self._ws_enabled:
            from src.api.websocket import manager
            await manager.broadcast("monitor_alert", alert_data)

        if self._email_enabled:
            subject = f"[Junk Detector Alert] Low score: {score:.0f}"
            title = item.get("title", "Unknown")
            body = f"Monitor alert: '{title}' scored {score:.0f}/100"
            self._send_email(subject, body)

    def _send_email(self, subject: str, body: str) -> None:
        """Send email notification via SMTP. Fails silently with logging."""
        try:
            smtp_host = self._email_config.get("smtp_host", "")
            smtp_port = self._email_config.get("smtp_port", 587)
            to_addr = self._email_config.get("to", "")
            smtp_username = self._email_config.get("smtp_username", "")
            smtp_password = self._email_config.get("smtp_password", "")

            if not smtp_host or not to_addr:
                logger.warning("Email not configured (missing smtp_host or to)")
                return

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"junk-detector@{smtp_host}"
            msg["To"] = to_addr

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                if smtp_username and smtp_password:
                    server.login(smtp_username, smtp_password)
                server.send_message(msg)

            logger.info("Email sent: %s", subject)
        except Exception as e:
            logger.warning("Email send failed: %s", e)

    async def send_webhook(self, payload: dict) -> bool:
        """POST score result to configured webhook URL with HMAC signature."""
        webhook_config = self._config.get("webhook", {})
        url = webhook_config.get("url")
        secret = webhook_config.get("secret", "")

        if not url:
            return False

        body = json.dumps(payload, ensure_ascii=False)
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Jianzhen-Signature": signature,
                    },
                    timeout=10.0,
                )
            return resp.status_code < 400
        except Exception as e:
            logger.warning("Webhook send failed: %s", e)
            return False
