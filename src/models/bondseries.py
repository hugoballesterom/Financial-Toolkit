from dataclasses import dataclass

import pandas as pd


@dataclass
class BondSeries:
    date: pd.DatetimeIndex
    ytm: pd.Series  # Porcentaje: 4.5 significa 4,5 %.

    def current_yield(self):
        return self.ytm.iloc[-1]

    def yield_change_bps(self):
        return self.ytm.diff() * 100

    def yield_max(self):
        return self.ytm.max()

    def yield_min(self):
        return self.ytm.min()