"""Aportaciones y retiradas externas; no son operaciones de mercado."""
from dataclasses import dataclass
from datetime import date as Date, datetime
from math import isfinite
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class CashMovement:
    movement_type: Literal["DEPOSIT", "WITHDRAW"]
    amount: float
    date: pd.Timestamp

    def __post_init__(self):
        if self.movement_type not in ("DEPOSIT", "WITHDRAW"):
            raise ValueError("Cash movement must be DEPOSIT or WITHDRAW")
        if isinstance(self.amount, bool):
            raise ValueError("Amount must be positive and finite")
        try:
            amount = float(self.amount)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Amount must be positive and finite") from exc
        if not isfinite(amount) or amount <= 0:
            raise ValueError("Amount must be positive and finite")
        if not isinstance(self.date, (str, Date, datetime, pd.Timestamp)):
            raise ValueError("Invalid cash movement date")
        date = pd.Timestamp(self.date)
        if pd.isna(date):
            raise ValueError("Invalid cash movement date")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "date", date.tz_localize(None).normalize())

    @property
    def cash_flow(self):
        return self.amount if self.movement_type == "DEPOSIT" else -self.amount
