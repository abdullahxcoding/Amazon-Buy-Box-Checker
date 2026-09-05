"""
Buy Box checker — core check logic, reused by both the desktop app
(desktop_app.py / analyzer.py, the primary way to run this) and this
module's own CLI entry point below (a manual/headless fallback for running
a single check from a terminal or an external scheduler, independent of
the desktop app).

For every ASIN given, checks who currently holds the Buy Box (via whichever
backend OFFER_SOURCE in .env selects — scraper today, sp_api later) and
triggers an alert if it's not Amazon, repeating that alert on every check
until Amazon wins the Buy Box back. If an expected_price is given for an
ASIN, also checks the current price against it (only while Amazon holds
the Buy Box — a vendor takeover is reported as that issue, not a price
mismatch) and alerts if they don't match, using the same repeat-until-
resolved pattern.
"""

import contextlib
import os
import random
import time

import config
from alerts import alert_lost, alert_recovered, alert_price_mismatch, alert_check_failed, logger
from csv_utils import read_asin_rows
from ip_guard import ensure_vpn_connected
from offer_sources import get_offer_source
from state_store import load_state, save_state

# Small float-rounding safety margin, not a "close enough" tolerance —
# prices are compared as exact currency values otherwise.
PRICE_TOLERANCE = 0.01

LOCK_PATH = os.path.join(config.BASE_DIR, "data", "check.lock")


@contextlib.contextmanager
def _run_lock():
    if os.path.exists(LOCK_PATH):
        logger.info("A check is already in progress (data/check.lock exists) — skipping this run.")
        yield False
        return
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "w") as f:
        f.write(str(time.time()))
    try:
        yield True
    finally:
        try:
            os.remove(LOCK_PATH)
        except FileNotFoundError:
            pass


def check_one(source, asin: str, label: str, expected_price, state: dict) -> dict:
    """Checks one ASIN, fires alerts/updates state as a side effect, and
    returns a small result dict describing what happened (used by the
    desktop app to update its live status table).

    expected_price is optional (None skips the price check for this ASIN,
    only the seller/Buy Box check runs)."""
    offer = source.get_buybox_offer(asin)

    if not offer.found:
        reason = offer.raw_note or "unknown reason"
        alert_check_failed(asin, label, reason)
        return {"asin": asin, "label": label, "expected_price": expected_price,
                "status": "check_failed", "detail": reason}

    prev = state.get(asin, {})
    was_status = prev.get("status", "ok")

    if not offer.is_sold_by_amazon:
        status = "alert"
        # Deliberately built from just the seller identity, not
        # offer.raw_note (which always tacks on price when found) — the
        # issue here is who holds the Buy Box, not the price, so the price
        # would be noise that makes the real problem harder to spot.
        detail = (f"Buy Box won by: {offer.seller_identifier}" if offer.seller_identifier
                  else offer.raw_note or "Amazon is no longer the Buy Box winner.")
        alert_lost(asin, label, offer)
    elif expected_price is not None and offer.price is not None and \
            abs(offer.price - expected_price) > PRICE_TOLERANCE:
        status = "price_mismatch"
        detail = f"Price mismatch: expected £{expected_price:.2f}, currently £{offer.price:.2f}"
        alert_price_mismatch(asin, label, offer, expected_price)
    else:
        status = "ok"
        if expected_price is not None and offer.price is None:
            detail = "Sold by Amazon (price not found on page — could not verify)"
        elif expected_price is not None:
            detail = f"Sold by Amazon at £{offer.price:.2f} (matches expected price)"
        else:
            detail = "Sold by Amazon"
        if was_status != "ok":
            alert_recovered(asin, label)

    state[asin] = {
        "status": status,
        "last_checked": time.time(),
        "last_seller": offer.seller_identifier,
        "last_price": offer.price,
        "expected_price": expected_price,
    }
    return {"asin": asin, "label": label, "expected_price": expected_price,
            "status": status, "detail": detail}


def main():
    """CLI entry point — a manual/headless fallback. The desktop app does
    NOT use this; it uses analyzer.py directly for interruptible timing."""
    with _run_lock() as acquired:
        if not acquired:
            return

        if config.OFFER_SOURCE == "scraper" and not ensure_vpn_connected():
            logger.error("Aborting run: VPN preflight check failed.")
            return

        asin_rows = read_asin_rows(config.ASIN_CSV_PATH)
        state = load_state()

        logger.info("Starting Buy Box check for %d ASIN(s) via %s", len(asin_rows), config.OFFER_SOURCE)
        with get_offer_source() as source:
            for i, row in enumerate(asin_rows):
                check_one(source, row["asin"], row["label"], row.get("expected_price"), state)

                if i < len(asin_rows) - 1:
                    delay = random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS)
                    time.sleep(delay)

        save_state(state)
        logger.info("Buy Box check complete")


if __name__ == "__main__":
    main()
