"""
notifier.py - Optional daily run notifications for operators.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

import requests


def notifications_enabled() -> bool:
    return bool(_slack_webhook_url() or _telegram_config() or _email_config())


def send_run_notification(
    all_results: dict[str, dict[str, Any]],
    *,
    summary_path: str,
    review_summary_path: str,
) -> dict[str, Any]:
    """Send configured notifications. Returns per-channel delivery status."""
    message = build_notification_message(
        all_results,
        summary_path=summary_path,
        review_summary_path=review_summary_path,
    )
    statuses = {}

    webhook_url = _slack_webhook_url()
    if webhook_url:
        statuses["slack"] = _send_slack(webhook_url, message)

    telegram = _telegram_config()
    if telegram:
        statuses["telegram"] = _send_telegram(telegram["bot_token"], telegram["chat_id"], message)

    email = _email_config()
    if email:
        statuses["email"] = _send_email(email, message, all_results)

    if not statuses:
        return {"enabled": False, "message": "No notification channels configured"}

    return {"enabled": True, "channels": statuses}


def build_notification_message(
    all_results: dict[str, dict[str, Any]],
    *,
    summary_path: str,
    review_summary_path: str,
) -> str:
    completed = [
        state_key for state_key, result in all_results.items()
        if result.get("upload_status") in {"success", "skipped"} and not result.get("error")
    ]
    failed = [
        state_key for state_key, result in all_results.items()
        if result.get("error")
    ]

    lines = [
        "Gold Price Bot daily run complete",
        f"Completed: {len(completed)} ({', '.join(completed) or 'none'})",
        f"Failed: {len(failed)} ({', '.join(failed) or 'none'})",
        "",
    ]

    for state_key, result in all_results.items():
        status = "failed" if result.get("error") else result.get("upload_status", "unknown")
        lines.append(f"{state_key}: {status}")
        if result.get("error"):
            lines.append(f"  error: {result['error']}")
        if result.get("video_path"):
            lines.append(f"  video: {result['video_path']}")
        if result.get("youtube_url"):
            lines.append(f"  youtube: {result['youtube_url']}")
        elif result.get("upload_skip_reason"):
            lines.append(f"  upload skipped: {result['upload_skip_reason']}")

    lines.extend(
        [
            "",
            f"Summary: {summary_path}",
            f"Review summary: {review_summary_path}",
        ]
    )
    return "\n".join(lines)


def _send_slack(webhook_url: str, message: str) -> dict[str, Any]:
    try:
        response = requests.post(webhook_url, json={"text": message}, timeout=15)
        response.raise_for_status()
        return {"ok": True, "status_code": response.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _send_telegram(bot_token: str, chat_id: str, message: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message[:4096]},
            timeout=15,
        )
        response.raise_for_status()
        return {"ok": True, "status_code": response.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _send_email(config: dict[str, Any], message: str, all_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    email = EmailMessage()
    email["Subject"] = _email_subject(all_results)
    email["From"] = config["from_addr"]
    email["To"] = ", ".join(config["to_addrs"])
    email.set_content(message)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=20) as smtp:
            if config["use_tls"]:
                smtp.starttls()
            if config["username"]:
                smtp.login(config["username"], config["password"])
            smtp.send_message(email)
        return {"ok": True, "recipients": len(config["to_addrs"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _email_subject(all_results: dict[str, dict[str, Any]]) -> str:
    failed = [state_key for state_key, result in all_results.items() if result.get("error")]
    if failed:
        return f"Gold Price Bot: {len(failed)} failed"
    return "Gold Price Bot: daily run complete"


def _slack_webhook_url() -> str:
    return os.environ.get("SLACK_WEBHOOK_URL", "").strip()


def _telegram_config() -> dict[str, str] | None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        return {"bot_token": bot_token, "chat_id": chat_id}
    return None


def _email_config() -> dict[str, Any] | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    from_addr = os.environ.get("EMAIL_FROM", "").strip()
    to_addrs = [
        addr.strip()
        for addr in os.environ.get("EMAIL_TO", "").split(",")
        if addr.strip()
    ]
    if not host or not from_addr or not to_addrs:
        return None
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        return None

    return {
        "host": host,
        "port": port,
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "use_tls": _env_bool("SMTP_USE_TLS", default=True),
        "from_addr": from_addr,
        "to_addrs": to_addrs,
    }


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
