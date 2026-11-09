from dataclasses import dataclass

import pandas as pd


@dataclass
class BondSeries:
    date: pd.DatetimeIndex
    ytm: pd.Series  # Percentage: 4.5 means 4.5 %.

    def current_yield(self):
        return self.ytm.iloc[-1]

    def yield_change_bps(self):
        return self.ytm.diff() * 100

    def yield_max(self):
        return self.ytm.max()

    def yield_min(self):
        return self.ytm.min()
    
    def yield_mean(self):
        """Mean yield of the interval, in percent."""
        return self.ytm.mean()

    def yield_change_total_bps(self):
        """Change between the last and the first yield, in basis points."""
        return (self.ytm.iloc[-1] - self.ytm.iloc[0]) * 100

    def yield_volatility(self):
        """Sample standard deviation of the yields, in percentage points."""
        return self.ytm.std()