"""Windows desktop toast notifications for Buy Box alerts.

Uses the "reminder" toast scenario (via raw Windows Toast XML, run through
PowerShell/WinRT — the same underlying technique the `winotify` package
uses, but hand-built here since winotify doesn't expose `scenario` or a
real system "Dismiss" action). A reminder-scenario toast does NOT
auto-expire after a few seconds like a normal toast — it stays on screen
and in the Action Center until the user explicitly dismisses it or clicks
an action, which is the point: an alert shouldn't be easy to miss.

Two actions are offered:
  - "Open"    — launches the app (frozen exe) or opens the project folder
                (running from source), so the user can go look at what's
                wrong.
  - "Dismiss" — a real system dismiss action; closes the toast and clears
                it from the Action Center, same as clicking the X.

Only shows anything while there's an active, logged-in desktop session on
this PC. If the hourly check is run by Task Scheduler configured to run
"whether user is logged on or not", no toast will appear (no desktop to
show it on) even though the check itself still runs and alerts still get
logged/emailed/shown on the dashboard as normal — see README for the
Task Scheduler setting this depends on.
"""

import logging
import subprocess
import sys

import config

logger = logging.getLogger("buybox_checker")

APP_ID = "Amazon Buy Box Checker"

_TOAST_PS_TEMPLATE = r'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$Template = @"
<toast scenario="reminder">
    <visual>
        <binding template="ToastImageAndText02">
            <text id="1"><![CDATA[{title}]]></text>
            <text id="2"><![CDATA[{msg}]]></text>
        </binding>
    </visual>
    <actions>
        <action activationType="protocol" content="Open" arguments="{launch_uri}" />
        <action activationType="system" content="Dismiss" arguments="dismiss" />
    </actions>
    <audio silent="false" />
</toast>
"@

$SerializedXml = New-Object Windows.Data.Xml.Dom.XmlDocument
$SerializedXml.LoadXml($Template)

$Toast = [Windows.UI.Notifications.ToastNotification]::new($SerializedXml)
$Toast.Tag = "{tag}"
$Toast.Group = "{app_id}"

$Notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{app_id}")
$Notifier.Show($Toast)
'''


def _xml_attr_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace('"', "&quot;")
                 .replace("<", "&lt;").replace(">", "&gt;"))


def _launch_uri() -> str:
    """file:/// URI to open when the toast's "Open" action is clicked —
    the app itself when frozen, otherwise the project folder (there's no
    single script to double-click when running from source)."""
    path = sys.executable if getattr(sys, "frozen", False) else config.BASE_DIR
    return "file:///" + path.replace("\\", "/")


def send_desktop_notification(title: str, message: str, tag: str = "") -> None:
    try:
        script = _TOAST_PS_TEMPLATE.format(
            title=title,
            msg=message,
            launch_uri=_xml_attr_escape(_launch_uri()),
            tag=_xml_attr_escape(tag or title)[:16],  # Windows caps tag length
            app_id=APP_ID,
        )
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            startupinfo=si,
        )
    except Exception:
        logger.exception("Failed to show desktop notification (no active desktop session, or PowerShell unavailable)")
