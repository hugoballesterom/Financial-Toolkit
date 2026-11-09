from dataclasses import dataclass, fields
from datetime import date
import logging
import math
import pandas as pd
import yfinance as yf
from .priceseries import PriceSeries
from .tokenomics import Tokenomics
from typing import Optional

@dataclass
class Cryptocurrency:
    name:str
    symbol: str
    blockchain: list[str]
    price: PriceSeries
    market_cap: Optional[float]
    market_cap_rank: Optional[int]
    tokenomics: Tokenomics
