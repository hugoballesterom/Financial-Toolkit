from dataclasses import dataclass

from .bondseries import BondSeries


@dataclass
class Bond:
    ticker: str
    name: str
    country: str
    maturity_years: float
    source: str
    series: BondSeries