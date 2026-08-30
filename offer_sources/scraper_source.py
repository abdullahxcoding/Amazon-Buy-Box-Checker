"""
Playwright-based scraper offer source.

Reads the live Amazon product page and pulls seller identity out of the buy
box. Amazon uses different wording on different marketplaces/UI versions:
  - Classic: "Sold by X" (sometimes "... and Ships from Y")
  - amazon.co.uk (current UI): a "Shipper / Seller" row showing one name
    when shipper and seller are the same (e.g. "Shipper / Seller  Amazon"),
    or separate "Shipper" and "Seller" rows when they differ.

This is inherently more fragile than SP-API: Amazon's markup/wording
changes, and pages can be CAPTCHA-walled. When no pattern matches, this
returns found=False with a raw_note explaining why (including a text
snippet for debugging), rather than guessing — check_buybox.py treats
"not found" as a failed check, logged but NOT alerted as a lost Buy Box
(to avoid false alarms from a blocked or unrecognized page).

IP rotation is handled at the OS level via a VPN connection (Privado),
not per-request here — connect the VPN before running check_buybox.py.
See ip_guard.py for the preflight check that verifies the VPN is actually
active before any scraping starts.
"""

import random
import re
import logging
import time

from playwright.sync_api import sync_playwright

import config
from offer_sources.base import OfferSource, BuyBoxOffer

logger = logging.getLogger("buybox_checker")

# A VPN connection can intermittently stall individual requests even while
# others succeed fine (congested/shared VPN server) — retry navigation a
# couple of times before giving up, rather than failing on the first hiccup.
MAX_NAVIGATION_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 4

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

CAPTCHA_MARKERS = [
    "Enter the characters you see below",
    "api-services-support@amazon.com",
    "/errors/validateCaptcha",
    "Click the button below to continue shopping",
    "To discuss automated access to Amazon data",
]

# Combined row: "Shipper / Seller" followed by one name (same line or next line).
COMBINED_SHIPPER_SELLER_RE = re.compile(r"Shipper\s*/\s*Seller\s*\n?\s*([^\n]{1,80})", re.IGNORECASE)
# Separate rows, used when shipper and seller differ.
SELLER_RE = re.compile(r"(?<!/)\bSeller\b\s*\n?\s*([^\n]{1,80})", re.IGNORECASE)
SHIPPER_RE = re.compile(r"\bShipper\b\s*\n?\s*([^\n]{1,80})", re.IGNORECASE)
# Classic wording fallback (older UI / other marketplaces).
SOLD_BY_RE = re.compile(r"Sold by[:\s]+([^.\n|]+?)(?:\s*and\s*Ships from|\s*\||$)", re.IGNORECASE)
FULFILLED_BY_AMAZON_RE = re.compile(r"Fulfilled by Amazon", re.IGNORECASE)


def _extract_shipper_seller(body_text: str):
    """Returns (shipper_name_or_None, seller_name_or_None)."""
    combined = COMBINED_SHIPPER_SELLER_RE.search(body_text)
    if combined:
        name = combined.group(1).strip()
        return name, name

    shipper_m = SHIPPER_RE.search(body_text)
    seller_m = SELLER_RE.search(body_text)
    shipper = shipper_m.group(1).strip() if shipper_m else None
    seller = seller_m.group(1).strip() if seller_m else None
    if shipper or seller:
        return shipper, seller

    classic = SOLD_BY_RE.search(body_text)
    if classic:
        return None, classic.group(1).strip()

    return None, None


def _debug_snippet(body_text: str) -> str:
    """Best-effort context around any seller-ish keyword, for troubleshooting."""
    for keyword in ("Shipper", "Seller", "Sold by", "Dispatches"):
        idx = body_text.find(keyword)
        if idx != -1:
            start = max(0, idx - 20)
            return body_text[start:idx + 100].replace("\n", " | ")
    return "(no Shipper/Seller/Sold by/Dispatches text found anywhere on page)"


class ScraperOfferSource(OfferSource):
    def _fetch_body_text(self, asin: str) -> tuple[str | None, str | None]:
        """Returns (body_text, None) on success, or (None, error_message)
        after exhausting retries. Only navigation/timeout failures are
        retried — those are the transient, VPN-flakiness kind."""
        url = f"https://www.{config.AMAZON_DOMAIN}/dp/{asin}"
        last_error = None

        for attempt in range(1, MAX_NAVIGATION_ATTEMPTS + 1):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=random.choice(USER_AGENTS),
                        viewport={"width": 1280, "height": 1000},
                        locale="en-US",
                    )
                    page = context.new_page()
                    try:
                        page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)
                        return page.inner_text("body"), None
                    except Exception as e:
                        last_error = str(e)
                        logger.warning("Scrape navigation attempt %d/%d failed for %s: %s",
                                        attempt, MAX_NAVIGATION_ATTEMPTS, asin, e)
                    finally:
                        context.close()
                finally:
                    browser.close()

            if attempt < MAX_NAVIGATION_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)

        logger.error("Scrape navigation failed for %s after %d attempts: %s",
                      asin, MAX_NAVIGATION_ATTEMPTS, last_error)
        return None, last_error

    def get_buybox_offer(self, asin: str) -> BuyBoxOffer:
        body_text, error = self._fetch_body_text(asin)
        if body_text is None:
            return BuyBoxOffer(asin=asin, found=False, is_sold_by_amazon=False,
                                raw_note=f"navigation error after {MAX_NAVIGATION_ATTEMPTS} attempts: {error}")

        if any(marker in body_text for marker in CAPTCHA_MARKERS):
            logger.warning("CAPTCHA/block page detected for %s", asin)
            return BuyBoxOffer(asin=asin, found=False, is_sold_by_amazon=False,
                                raw_note="blocked by CAPTCHA/anti-bot page")

        shipper_name, seller_name = _extract_shipper_seller(body_text)
        if seller_name is None:
            snippet = _debug_snippet(body_text)
            logger.warning("Could not find seller text for %s -- context: %s", asin, snippet)
            return BuyBoxOffer(asin=asin, found=False, is_sold_by_amazon=False,
                                raw_note=f"seller text not found on page (layout change or no buy box). "
                                         f"Context: {snippet}")

        is_amazon = seller_name.lower() == config.AMAZON_SELLER_NAME.lower()
        is_fba = (
            (shipper_name is not None and shipper_name.lower() == config.AMAZON_SELLER_NAME.lower())
            or bool(FULFILLED_BY_AMAZON_RE.search(body_text))
            or is_amazon
        )

        detail = f"Seller: {seller_name}"
        if shipper_name and shipper_name != seller_name:
            detail += f" | Shipper: {shipper_name}"

        return BuyBoxOffer(
            asin=asin,
            found=True,
            is_sold_by_amazon=is_amazon,
            seller_identifier=seller_name,
            is_fulfilled_by_amazon=is_fba,
            raw_note=detail,
        )
