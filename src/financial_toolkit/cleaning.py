"""Cleaning of a single asset's price series.

Prices are cleaned one asset at a time: no frequency change and no filling.
Days without a row are days without trading, and a row with a missing close
is a broken record, so it is dropped instead of filled (filling would invent
a price and a false zero return). Aligning assets with different calendars
is a separate step.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .priceseries import PriceSeries

# Same threshold as BondNormalizer.MAX_MISSING_RATIO.
MAX_MISSING_RATIO = 0.05

_COLUMNS = ('open', 'high', 'low', 'close', 'volume')


@dataclass(frozen=True)
class CleaningReport:
    """What clean_prices changed in a price series.

    Attributes:
        n_input: Rows received.
        n_output: Rows kept.
        invalid_dates: Rows dropped because their date was missing (NaT).
        duplicates: Rows dropped because their timestamp was repeated
            (the last one is kept).
        missing: Rows dropped because the close was missing, infinite or
            not positive.
        timezone: Original timezone of the dates, or None if they had none.
    """

    n_input: int
    n_output: int
    invalid_dates: int
    duplicates: int
    missing: int
    timezone: str | None

    @property
    def n_dropped(self) -> int:
        """Total rows dropped."""
        return self.n_input - self.n_output


def clean_prices(
    prices: PriceSeries,
    max_missing: float = MAX_MISSING_RATIO,
) -> tuple[PriceSeries, CleaningReport]:
    """Clean a price series and report what was changed.

    Steps: drop the timezone (keeping the local exchange time), drop invalid
    dates, sort, drop repeated timestamps keeping the last one, convert the
    columns to numbers and drop the rows whose close is missing, infinite or
    not positive.

    Args:
        prices: Price series as returned by a fetcher.
        max_missing: Highest share of rows with an invalid close that is
            still accepted, between 0 and 1.

    Returns:
        The clean series (a new object) and the report.

    Raises:
        TypeError: If prices is not a PriceSeries.
        ValueError: If max_missing is not between 0 and 1, the share of
            invalid closes is above max_missing or no rows are left.
    """
    if not isinstance(prices, PriceSeries):
        raise TypeError(f"prices must be a PriceSeries, got {type(prices).__name__}")
    if isinstance(max_missing, bool) or not 0 <= max_missing <= 1:
        raise ValueError(f"max_missing must be between 0 and 1, got {max_missing!r}")

    columns = {
        name: getattr(prices, name)
        for name in _COLUMNS
        if getattr(prices, name) is not None
    }
    table = pd.DataFrame(columns)
    n_input = len(table)

    # 1. Dates: drop the timezone and the invalid ones.
    index = pd.DatetimeIndex(table.index)
    timezone = None if index.tz is None else str(index.tz)
    if index.tz is not None:
        index = index.tz_localize(None)
    table.index = index
    invalid_dates = int(index.isna().sum())
    table = table.loc[index.notna()]

    # 2. Sort and keep the last row of each repeated timestamp.
    table = table.sort_index(kind='stable')
    repeated = table.index.duplicated(keep='last')
    duplicates = int(repeated.sum())
    table = table.loc[~repeated]

    # 3. Numbers; an infinite or non-positive close counts as missing.
    table = table.apply(pd.to_numeric, errors='coerce')
    close = table['close']
    invalid = close.isna() | np.isinf(close) | (close <= 0)
    if len(table) and invalid.mean() > max_missing:
        raise ValueError(
            f"missing closes must be at most {max_missing:.0%}, "
            f"got {invalid.mean():.2%} ({int(invalid.sum())} of {len(table)})"
        )
    missing = int(invalid.sum())
    table = table.loc[~invalid]

    if table.empty:
        raise ValueError("prices must have at least one valid close, got none")

    table.index.name = 'date'
    clean = replace(
        prices,
        date=table.index,
        **{name: table[name] if name in table else None for name in _COLUMNS},
    )
    report = CleaningReport(
        n_input=n_input,
        n_output=len(table),
        invalid_dates=invalid_dates,
        duplicates=duplicates,
        missing=missing,
        timezone=timezone,
    )
    return clean, report
