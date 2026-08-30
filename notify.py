"""Windows desktop toast notifications for Buy Box alerts.

Only shows anything while there's an active, logged-in desktop session on
this PC. If the hourly check is run by Task Scheduler configured to run
"whether user is logged on or not", no toast will appear (no desktop to
show it on) even though the check itself still runs and alerts still get
logged/emailed/shown on the dashboard as normal — see README for the
Task Scheduler setting this depends on.
"""

import logging

logger = logging.getLogger("buybox_checker")


def send_desktop_notification(title: str, message: str) -> None:
    try:
        from winotify import Notification

        toast = Notification(
            app_id="Amazon Buy Box Checker",
            title=title,
            msg=message,
            duration="long",
        )
        toast.show()
    except Exception:
        logger.exception("Failed to show desktop notification (no active desktop session, or winotify unavailable)")
