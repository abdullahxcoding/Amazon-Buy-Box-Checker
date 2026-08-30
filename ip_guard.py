"""
Preflight check: confirms traffic is actually going through the VPN before
the scraper hits Amazon. Since Privado VPN routes the whole machine's
traffic through one IP at a time (not a per-request proxy pool), the only
safety net against accidentally scraping from your raw home IP is to check
the current public IP before each run and compare it against your known
home IP.

Set HOME_IP in .env (your normal, non-VPN public IP) to enable this check.
If it's left blank, the check is skipped and the current IP is just logged
for your own visual confirmation in logs/checker.log.
"""

import logging
import urllib.request

import config

logger = logging.getLogger("buybox_checker")

_IP_CHECK_URL = "https://api.ipify.org"


def get_public_ip(timeout: int = 10) -> str | None:
    try:
        with urllib.request.urlopen(_IP_CHECK_URL, timeout=timeout) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as e:
        logger.error("Could not determine current public IP: %s", e)
        return None


def ensure_vpn_connected() -> bool:
    """
    Returns True if it's safe to proceed with scraping, False if the run
    should be aborted (VPN appears to be disconnected).
    """
    ip = get_public_ip()
    if ip is None:
        logger.warning("Skipping VPN check (could not reach IP-check service); proceeding anyway.")
        return True

    logger.info("Current public IP for this run: %s", ip)

    if not config.HOME_IP:
        logger.info("HOME_IP not set in .env, so VPN-connected status cannot be verified automatically. "
                     "Confirm manually that Privado VPN is connected before scheduled runs.")
        return True

    if ip == config.HOME_IP:
        logger.error("Current public IP matches HOME_IP (%s) — Privado VPN does not appear to be connected. "
                      "Aborting this run to avoid scraping Amazon from your raw IP.", config.HOME_IP)
        return False

    return True
