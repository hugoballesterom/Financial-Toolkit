from dataclasses import dataclass, field

import pandas as pd
from pandas.api.types import is_numeric_dtype


@dataclass(kw_only=True)
class MacroSeries:
    """Single version of a macroeconomic time series plus its metadata.

    Wraps a numeric pd.Series indexed by date (reference period) and
    computes basic summary statistics on creation.

    Attributes:
        data: Values indexed by a pd.DatetimeIndex, sorted ascending.
        series_id: Identifier in the source (e.g. "UNRATE" in FRED).
        release: Which version of the data. An int n is the n-th
            release (1 = first publication), "latest" the most recent
            version, and a pd.Timestamp the latest version published
            up to that date.
        mean, std: Computed from data.
        start, end: First and last dates in data.
        n_obs: Number of non-null observations.

    Raises:
        TypeError: If data is not a pd.Series or its index is not a
            pd.DatetimeIndex.
        ValueError: If data is empty or not numeric.
    """

    data: pd.Series = field(repr=False, compare=False)
    series_id: str
    name: str
    source: str
    frequency: str
    unit: str
    country: str
    category: str # TODO: replace with an Enum once categories are fixed
    release: int | str | pd.Timestamp = 'latest'
    mean: float = field(init=False)
    std: float = field(init=False)
    start: pd.Timestamp = field(init=False)
    end: pd.Timestamp = field(init=False)
    n_obs: int = field(init=False)

    def __post_init__(self) -> None:
        """Validate data and compute summary statistics."""

        if not isinstance(self.data, pd.Series):
            raise TypeError(f"data must be a Series, got {type(self.data).__name__}")
        
        if not isinstance(self.data.index, pd.DatetimeIndex):
            raise TypeError(f"index must be a pd.DatetimeIndex, got {type(self.data.index).__name__}")
        
        if self.data.empty:
            raise ValueError("data cannot be empty")

        if not is_numeric_dtype(self.data):
            raise ValueError(f"data values must be numeric, got dtype {self.data.dtype}")

        # Sources may return dates unordered and start/end rely on sorted index
        self.data = self.data.sort_index()

        self.mean = self.data.mean()

        # std is the sample std (n-1)
        self.std = self.data.std()
        self.start = self.data.index[0]
        self.end = self.data.index[-1]

        # count() ignores NaN
        self.n_obs = self.data.count()