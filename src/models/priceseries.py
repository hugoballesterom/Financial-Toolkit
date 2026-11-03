from dataclasses import dataclass
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

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({
        "Open": self.open.to_numpy(),
        "High": self.high.to_numpy(),
        "Low": self.low.to_numpy(),
        "Close": self.close.to_numpy(),
        "Volume": self.volume.to_numpy()
        }, index=self.date)

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