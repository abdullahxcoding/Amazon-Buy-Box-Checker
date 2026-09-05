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

def _label_line(label: str) -> re.Pattern:
    """A label that is the WHOLE line, with its value on the next line.
    Anchoring this way (rather than a loose \\bWORD\\b anywhere in the
    flattened page text) is deliberate: Amazon's boilerplate elsewhere on
    the page contains the bare words "Seller"/"Shipper" mid-sentence (e.g.
    "Brand Registry and New Seller Incentives", "Seller Fulfilled Prime",
    "#1 Best Seller") which a loose match would wrongly treat as the
    buy-box seller name — this bit us in production (falsely reporting a
    seller of "Incentives" on every check, from the "New Seller
    Incentives" footer link). Requiring the label to be alone on its own
    line excludes all of those, since none of them have "Seller"/"Shipper"
    as the entire line."""
    return re.compile(rf"^{label}\s*$\n\s*(.{{1,80}})\s*$", re.IGNORECASE | re.MULTILINE)


# Combined row: "Shipper / Seller" alone on a line, value on the next line.
COMBINED_SHIPPER_SELLER_RE = _label_line(r"Shipper\s*/\s*Seller")
# Separate rows, used when shipper and seller differ.
SHIPPER_RE = _label_line(r"Shipper")
SELLER_RE = _label_line(r"Seller")
# Alternate current UI layout seen on some product pages/categories:
# "Dispatches from" / "Sold by" as their own separate label lines instead
# of "Shipper" / "Seller".
DISPATCHES_FROM_RE = _label_line(r"Dispatches from")
SOLD_BY_LINE_RE = _label_line(r"Sold by")
# Classic inline wording fallback (older UI / other marketplaces): "Sold by
# X" with the name on the SAME line, optionally followed by "and Ships
# from Y". Deliberately last-resort and not line-anchored, since this
# format doesn't have the label-alone-on-its-line shape the others do.
SOLD_BY_RE = re.compile(r"Sold by[:\s]+([^.\n|]+?)(?:\s*and\s*Ships from|\s*\||$)", re.IGNORECASE)
FULFILLED_BY_AMAZON_RE = re.compile(r"Fulfilled by Amazon", re.IGNORECASE)

# Selector-based (not regex-on-body-text) because a product page can show
# several prices at once (RRP struck through, gift-card-discounted price,
# "other sellers from" price) — picking the wrong one from flattened text
# would silently compare against garbage. :not(.a-text-price) excludes the
# struck-through "was" price; these are the standard containers Amazon uses
# for the actual current Buy Box price.
PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen",
    "#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen",
    "#tp_price_block_total_price_ww .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
]
PRICE_NUM_RE = re.compile(r"(\d[\d,]*\.\d{2})")


def _parse_price_text(text: str) -> float | None:
    m = PRICE_NUM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_price(page) -> float | None:
    for selector in PRICE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.text_content(timeout=2000)
            if not text:
                continue
            price = _parse_price_text(text)
            if price is not None:
                return price
        except Exception:
            continue
    return None


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

    dispatches_m = DISPATCHES_FROM_RE.search(body_text)
    sold_by_line_m = SOLD_BY_LINE_RE.search(body_text)
    dispatches = dispatches_m.group(1).strip() if dispatches_m else None
    sold_by_line = sold_by_line_m.group(1).strip() if sold_by_line_m else None
    if dispatches or sold_by_line:
        return dispatches, sold_by_line

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
    """Keeps one Playwright + browser process alive across an entire check
    cycle (use as `with ScraperOfferSource() as source:`) instead of
    launching/closing a fresh browser per ASIN — with 1000 ASINs, that
    launch overhead alone previously added up to real minutes. Each ASIN
    still gets its own fresh browser *context* (cheap — no new process,
    just a clean cookie/session slate), so isolation between checks is
    unchanged. If the shared browser ever crashes mid-cycle, it's detected
    and relaunched automatically on the next attempt.

    Falls back to working correctly even if used without `with` (lazily
    launches the browser on first use) — but then never closes it itself,
    so callers should always use the context-manager form in a check loop.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self._ensure_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_browser()
        return False

    def _ensure_browser(self):
        if self._browser is not None and self._browser.is_connected():
            return
        self._close_browser()
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def _close_browser(self):
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _fetch_page_data(self, asin: str) -> tuple[str | None, float | None, str | None]:
        """Returns (body_text, price, None) on success, or (None, None,
        error_message) after exhausting retries. Only navigation/timeout
        failures are retried — those are the transient, VPN-flakiness kind.
        price may be None on success too (page loaded fine, price simply
        wasn't found by any selector) — that's not treated as a failure."""
        url = f"https://www.{config.AMAZON_DOMAIN}/dp/{asin}"
        last_error = None

        for attempt in range(1, MAX_NAVIGATION_ATTEMPTS + 1):
            try:
                self._ensure_browser()
                context = self._browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1280, "height": 1000},
                    locale="en-US",
                )
                try:
                    page = context.new_page()
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    body_text = page.inner_text("body")
                    price = _extract_price(page)
                    return body_text, price, None
                finally:
                    context.close()
            except Exception as e:
                # Covers navigation/timeout failures AND the shared browser
                # having crashed/disconnected — both are worth retrying.
                # Some exceptions (certain Playwright internal errors, a
                # crashed browser process) stringify to an empty message —
                # fall back to repr()/type name so the log and UI always
                # show something diagnosable instead of a blank string.
                last_error = str(e) or repr(e) or f"{type(e).__name__} (no error message)"
                logger.warning("Scrape attempt %d/%d failed for %s: %s",
                                attempt, MAX_NAVIGATION_ATTEMPTS, asin, last_error)
                # Force a relaunch on the next attempt in case the browser
                # process itself is what's actually broken.
                self._close_browser()

            if attempt < MAX_NAVIGATION_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)

        logger.error("Scrape navigation failed for %s after %d attempts: %s",
                      asin, MAX_NAVIGATION_ATTEMPTS, last_error)
        return None, None, last_error

    def get_buybox_offer(self, asin: str) -> BuyBoxOffer:
        body_text, price, error = self._fetch_page_data(asin)
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
        if price is not None:
            detail += f" | Price: £{price:.2f}"

        return BuyBoxOffer(
            asin=asin,
            found=True,
            is_sold_by_amazon=is_amazon,
            seller_identifier=seller_name,
            is_fulfilled_by_amazon=is_fba,
            price=price,
            raw_note=detail,
        )
