from dataclasses import dataclass
from math import isfinite
from typing import Literal

import pandas as pd

from .stock import Stock
from .index import Index
from .cryptocurrency import Cryptocurrency


# Bonds are yield series, not prices: fixed income enters a portfolio
# through bond ETFs (for example IEF or TLT) downloaded as stocks.
Asset = Stock | Index | Cryptocurrency
ALLOWED_TYPES = (Stock, Index, Cryptocurrency)


@dataclass
class Transaction:
    asset: Asset
    transaction_type: Literal["BUY", "SELL"]
    quantity: float
    price: float
    date: pd.Timestamp

    def __post_init__(self):
        if not isinstance(self.asset, ALLOWED_TYPES):
            raise TypeError("Invalid asset type")

        if self.transaction_type not in ("BUY", "SELL"):
            raise ValueError("Transaction type must be BUY or SELL")

        for name in ("quantity", "price"):
            value = getattr(self, name)

            if isinstance(value, bool):
                raise ValueError(f"{name} must be a positive finite number")

            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    f"{name} must be a positive finite number"
                ) from exc

            if not isfinite(value) or value <= 0:
                raise ValueError(
                    f"{name} must be a positive finite number"
                )

            setattr(self, name, value)

        if not isinstance(self.date, (str, pd.Timestamp)):
            from datetime import date, datetime

            if not isinstance(self.date, (date, datetime)):
                raise ValueError("Invalid transaction date")

        try:
            transaction_date = pd.Timestamp(self.date)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid transaction date") from exc

        if pd.isna(transaction_date):
            raise ValueError("Invalid transaction date")

        if transaction_date.tzinfo is not None:
            transaction_date = transaction_date.tz_localize(None)

        self.date = transaction_date.normalize()

    @property
    def total_value(self) -> float:
        """Amount of the trade, always positive."""
        return self.quantity * self.price

    @property
    def signed_quantity(self) -> float:
        """Change in the units held."""
        if self.transaction_type == "BUY":
            return self.quantity

        return -self.quantity

    @property
    def cash_flow(self) -> float:
        """Change in cash, without fees."""
        if self.transaction_type == "BUY":
            return -self.total_value

        return self.total_value