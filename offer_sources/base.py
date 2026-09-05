from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class BuyBoxOffer:
    """Normalized result, identical shape regardless of which source produced it."""
    asin: str
    found: bool                    # False if no buy box / offer could be determined
    is_sold_by_amazon: bool        # the actual trigger condition
    seller_identifier: Optional[str] = None   # SellerId (sp_api) or seller name text (scraper)
    is_fulfilled_by_amazon: Optional[bool] = None
    price: Optional[float] = None
    raw_note: Optional[str] = None  # free-text detail for alert messages


class OfferSource(ABC):
    """A check cycle does `with get_offer_source() as source:` around its
    per-ASIN loop. __enter__/__exit__ let a source hold an expensive
    resource open across the whole cycle instead of setting it up and
    tearing it down per ASIN (e.g. the scraper keeps one browser process
    running for the whole cycle instead of launching a fresh one per ASIN).
    Default no-op — sources with nothing to persist (like SP-API) don't
    need to override these."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @abstractmethod
    def get_buybox_offer(self, asin: str) -> BuyBoxOffer:
        ...
