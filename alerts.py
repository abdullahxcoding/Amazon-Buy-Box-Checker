import json
import logging
import os
import smtplib
import time
from email.mime.text import MIMEText

import config
from notify import send_desktop_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("buybox_checker")


def send_email(subject: str, body: str) -> None:
    if not config.EMAIL_ENABLED:
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.ALERT_EMAIL_FROM
    msg["To"] = config.ALERT_EMAIL_TO
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.ALERT_EMAIL_FROM, [config.ALERT_EMAIL_TO], msg.as_string())
    except Exception:
        logger.exception("Failed to send alert email")


def _record_history(asin: str, label: str, event: str, detail: str) -> None:
    """Appends one JSON line per event, for the dashboard's history view."""
    os.makedirs(os.path.dirname(config.ALERTS_HISTORY_PATH), exist_ok=True)
    entry = {"ts": time.time(), "asin": asin, "label": label, "event": event, "detail": detail}
    with open(config.ALERTS_HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def alert_lost(asin: str, label: str, offer) -> None:
    detail = offer.raw_note or "Amazon is no longer the Buy Box winner."
    subject = f"[Buy Box ALERT] {label or asin} is NO LONGER sold by Amazon"
    body = (
        f"ASIN: {asin}\n"
        f"Label: {label}\n"
        f"{detail}\n\n"
        f"This alert will keep repeating on every hourly check until the Amazon "
        f"offer is back as the Buy Box winner."
    )
    logger.warning("LOST: %s (%s) -- %s", asin, label, detail)
    _record_history(asin, label, "lost", detail)
    send_email(subject, body)
    send_desktop_notification(f"Buy Box lost: {label or asin}", detail)


def alert_price_mismatch(asin: str, label: str, offer, expected_price: float) -> None:
    detail = f"Price mismatch: expected £{expected_price:.2f}, currently £{offer.price:.2f}"
    subject = f"[Price ALERT] {label or asin} price does not match"
    body = (
        f"ASIN: {asin}\n"
        f"Label: {label}\n"
        f"{detail}\n\n"
        f"Seller is still Amazon, but the price doesn't match what you set as the "
        f"expected price. This alert will keep repeating on every check until the "
        f"price matches again."
    )
    logger.warning("PRICE MISMATCH: %s (%s) -- %s", asin, label, detail)
    _record_history(asin, label, "price_mismatch", detail)
    send_email(subject, body)
    send_desktop_notification(f"Price mismatch: {label or asin}", detail)


def alert_recovered(asin: str, label: str) -> None:
    detail = "Listing is back to normal (sold by Amazon, price matches if set)."
    subject = f"[RESOLVED] {label or asin} is back to normal"
    body = f"ASIN: {asin}\nLabel: {label}\n{detail}"
    logger.info("RECOVERED: %s (%s)", asin, label)
    _record_history(asin, label, "recovered", detail)
    send_email(subject, body)
    send_desktop_notification(f"Resolved: {label or asin}", detail)


def alert_check_failed(asin: str, label: str, reason: str) -> None:
    logger.warning("CHECK FAILED (no alert fired): %s (%s) -- %s", asin, label, reason)
    _record_history(asin, label, "check_failed", reason)
