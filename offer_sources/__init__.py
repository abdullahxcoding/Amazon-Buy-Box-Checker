"""
Factory for the "offer source" — whatever backend answers the question
"who currently holds the Buy Box for this ASIN, and is it Amazon?".

Swapping OFFER_SOURCE in .env from "scraper" to "sp_api" is the only change
needed to move from web scraping to the official SP-API once that access is
granted. check_buybox.py never talks to Playwright or SP-API directly — it
only calls get_offer_source().get_buybox_offer(asin).
"""

import config


def get_offer_source():
    if config.OFFER_SOURCE == "scraper":
        from offer_sources.scraper_source import ScraperOfferSource
        return ScraperOfferSource()
    elif config.OFFER_SOURCE == "sp_api":
        from offer_sources.sp_api_source import SpApiOfferSource
        return SpApiOfferSource()
    else:
        raise ValueError(f"Unknown OFFER_SOURCE: {config.OFFER_SOURCE!r} (expected 'scraper' or 'sp_api')")
