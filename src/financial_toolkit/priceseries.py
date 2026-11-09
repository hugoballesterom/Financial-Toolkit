from dataclasses import dataclass, field
import pandas as pd
import numpy as np


@dataclass
class PriceSeries:

    date: pd.DatetimeIndex
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series

    # Basic statistics of the log returns, computed when the series is created.
    mean_return: float = field(init=False)
    volatility: float = field(init=False)
    periods_per_year: float = field(init=False)
    annual_return: float = field(init=False)
    annual_volatility: float = field(init=False)

    def __post_init__(self):
        if not pd.Index(self.date).equals(self.close.index):
            raise ValueError("date must match the index of close")

        self.mean_return = float(self.compute_mean_return())
        self.volatility = float(self.compute_volatility())

        # Same convention as Portfolio: 365 days over the mean interval.
        intervals = pd.Series(pd.Index(self.date)).diff().dt.days
        mean_days = intervals.mean()
        self.periods_per_year = 365 / mean_days if mean_days > 0 else np.nan
        self.annual_return = self.mean_return * self.periods_per_year
        self.annual_volatility = self.volatility * np.sqrt(self.periods_per_year)

    def to_dataframe(self) -> pd.DataFrame:
        """OHLCV table indexed by date; columns that are None are left out."""
        columns = {
            "Open": self.open,
            "High": self.high,
            "Low": self.low,
            "Close": self.close,
            "Volume": self.volume,
        }
        table = pd.DataFrame(
            {name: values for name, values in columns.items() if values is not None}
        )
        table.index.name = "date"
        return table

    def current_price(self):
        return self.close.iloc[-1]

    def compute_return(self):
        return np.log(self.close / self.close.shift(1))

    def cumulative_return(self):
        return np.exp(self.compute_return().sum()) - 1

    def compute_mean_return(self):
        return self.compute_return().mean()

    def compute_volatility(self):
        return self.compute_return().std()

    def max_price(self):
        return self.close.max()

    def min_price(self):
        return self.close.min()

    def sma(self, window: int = 50):
        return self.close.rolling(window=window).mean()

    def ema(self, window: int = 20):
        return self.close.ewm(span=window, adjust=False).mean()

    def macd(self):

        macd = self.ema(12) - self.ema(26)
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        return pd.DataFrame({
            "MACD": macd,
            "Signal": signal,
            "Histogram": histogram
        })

    def rsi(self, window: int = 14):

        changes = self.close.diff()

        gains = changes.clip(lower=0)
        losses = -changes.clip(upper=0)

        avg_gains = gains.ewm(alpha=1/window, adjust=False, min_periods=window).mean()
        avg_losses = losses.ewm(alpha=1/window, adjust=False, min_periods=window).mean()

        rs = avg_gains / avg_losses

        return 100 - (100 / (1 + rs))

    def bollinger_bands(self, window: int = 20, std: float = 2):

        middle = self.sma(window)
        volatility = self.close.rolling(window=window).std()

        upper = middle + std * volatility
        lower = middle - std * volatility

        return pd.DataFrame({
            "Upper": upper,
            "Middle": middle,
            "Lower": lower
        })

    def compute_drawdown(self):
        return self.close / self.close.cummax() - 1

    def max_drawdown(self):
        return self.compute_drawdown().min()