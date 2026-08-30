"""
SP-API-based offer source — the future replacement for the scraper once
Pricing-role SP-API access is available.

Not implemented yet. To activate:
  1. pip install python-amazon-sp-api
  2. Fill in the SP-API credentials in .env
  3. Implement get_buybox_offer() below using Products.get_item_offers(),
     matching the same BuyBoxOffer shape the scraper returns (see
     offer_sources/base.py and offer_sources/scraper_source.py for
     reference — the rest of the system does not need to change).
  4. Set OFFER_SOURCE=sp_api in .env.
"""

import config
from offer_sources.base import OfferSource, BuyBoxOffer


class SpApiOfferSource(OfferSource):
    def get_buybox_offer(self, asin: str) -> BuyBoxOffer:
        raise NotImplementedError(
            "SP-API offer source is not implemented yet. See the module "
            "docstring in offer_sources/sp_api_source.py for what to fill in "
            "once Pricing-role SP-API access is granted."
        )
