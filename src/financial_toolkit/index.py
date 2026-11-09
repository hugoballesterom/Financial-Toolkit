from dataclasses import dataclass
from typing import Optional
import pandas as pd

from .priceseries import PriceSeries


@dataclass
class Index:
    name: str
    symbol: str
    country: Optional[str]
    currency: Optional[str]
    exchange: Optional[str]
    price: PriceSeries
    constituents: Optional[pd.DataFrame] = None
    sector_weights: Optional[dict] = None