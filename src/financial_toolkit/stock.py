from dataclasses import dataclass, field
import pandas as pd
from .company import Company
from .priceseries import PriceSeries


@dataclass
class Stock:
    ticker:str
    price: PriceSeries
    company: Company
    currency: str | None = None
