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
    @abstractmethod
    def get_buybox_offer(self, asin: str) -> BuyBoxOffer:
        ...
