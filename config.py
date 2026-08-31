import os
import sys
from dotenv import load_dotenv

# Anchor all relative paths to where the app actually lives, not the
# current working directory — cwd is unreliable once this runs as a
# packaged .exe (varies by how it's launched: double-click, shortcut with
# a different "Start in" folder, Task Scheduler, etc.). sys.executable is
# the real .exe location when frozen by PyInstaller; __file__ otherwise.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# The packaged .exe bundles the actual Chromium browser inside itself (see
# build_exe.ps1's --add-data) so it's fully self-contained on any device —
# no separate browser install step. PyInstaller's onefile mode extracts
# bundled data to a temporary folder (sys._MEIPASS) at startup; if that
# extracted copy is present, point Playwright at it directly. Otherwise
# (running from source, or a build without a bundled browser) fall back to
# the normal shared install location, same as a regular `playwright install
# chromium` would use.
_bundled_browsers = os.path.join(getattr(sys, "_MEIPASS", ""), "ms-playwright")
if getattr(sys, "frozen", False) and os.path.isdir(_bundled_browsers):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _bundled_browsers
else:
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright"),
    )

OFFER_SOURCE = os.getenv("OFFER_SOURCE", "scraper").strip().lower()

# --- Scraper settings ---
# IP rotation is handled by connecting Privado VPN at the OS level before
# running the checker (see ip_guard.py) — not a per-request proxy pool.
HOME_IP = os.getenv("HOME_IP", "").strip()
MIN_DELAY_SECONDS = float(os.getenv("MIN_DELAY_SECONDS", "8"))
MAX_DELAY_SECONDS = float(os.getenv("MAX_DELAY_SECONDS", "20"))
# This project only ever targets amazon.co.uk — hardcoded as the real
# default (not just an .env fallback) so the app behaves correctly out of
# the box even if the .exe is copied to another machine without its .env.
AMAZON_DOMAIN = os.getenv("AMAZON_DOMAIN", "amazon.co.uk").strip()

# --- SP-API settings ---
MARKETPLACE = os.getenv("MARKETPLACE", "UK")
SP_API_CREDENTIALS = {
    "refresh_token": os.getenv("SP_API_REFRESH_TOKEN"),
    "lwa_app_id": os.getenv("LWA_APP_ID"),
    "lwa_client_secret": os.getenv("LWA_CLIENT_SECRET"),
    "aws_access_key": os.getenv("AWS_ACCESS_KEY"),
    "aws_secret_key": os.getenv("AWS_SECRET_KEY"),
    "role_arn": os.getenv("ROLE_ARN"),
}

# --- Shared "who is Amazon" identity ---
AMAZON_SELLER_ID = os.getenv("AMAZON_SELLER_ID", "").strip()
# Confirmed via live screenshot: amazon.co.uk's Shipper/Seller block shows
# exactly "Amazon" (not "Amazon.co.uk").
AMAZON_SELLER_NAME = os.getenv("AMAZON_SELLER_NAME", "Amazon").strip()

# --- Email alerting ---
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "").strip()
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "").strip()
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and ALERT_EMAIL_FROM and ALERT_EMAIL_TO)

# --- Paths ---
ASIN_CSV_PATH = os.path.join(BASE_DIR, "data", "asins.csv")
STATE_JSON_PATH = os.path.join(BASE_DIR, "data", "state.json")
ALERTS_HISTORY_PATH = os.path.join(BASE_DIR, "data", "alerts_history.jsonl")
LOG_PATH = os.path.join(BASE_DIR, "logs", "checker.log")

# On a fresh machine where only the built .exe was copied over (not the
# whole project folder), data/ and logs/ won't exist yet — create them
# on first run instead of crashing the moment something tries to write
# a log or state file into a missing directory.
os.makedirs(os.path.dirname(ASIN_CSV_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
