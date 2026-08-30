import os
from dotenv import load_dotenv

load_dotenv()

OFFER_SOURCE = os.getenv("OFFER_SOURCE", "scraper").strip().lower()

# --- Scraper settings ---
# IP rotation is handled by connecting Privado VPN at the OS level before
# running the checker (see ip_guard.py) — not a per-request proxy pool.
HOME_IP = os.getenv("HOME_IP", "").strip()
MIN_DELAY_SECONDS = float(os.getenv("MIN_DELAY_SECONDS", "8"))
MAX_DELAY_SECONDS = float(os.getenv("MAX_DELAY_SECONDS", "20"))
AMAZON_DOMAIN = os.getenv("AMAZON_DOMAIN", "amazon.com").strip()

# --- SP-API settings ---
MARKETPLACE = os.getenv("MARKETPLACE", "US")
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
AMAZON_SELLER_NAME = os.getenv("AMAZON_SELLER_NAME", "Amazon.com").strip()

# --- Email alerting ---
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "").strip()
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "").strip()
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and ALERT_EMAIL_FROM and ALERT_EMAIL_TO)

# --- Paths ---
ASIN_CSV_PATH = os.path.join("data", "asins.csv")
STATE_JSON_PATH = os.path.join("data", "state.json")
ALERTS_HISTORY_PATH = os.path.join("data", "alerts_history.jsonl")
LOG_PATH = os.path.join("logs", "checker.log")
