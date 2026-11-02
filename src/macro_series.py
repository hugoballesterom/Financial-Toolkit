from dataclasses import dataclass, field
from datetime import datetime
from numbers import Integral

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_string_dtype

from enums import Frequency


def parse_release(release: int | str | datetime) -> int | str | pd.Timestamp:
    """Validate a release selector and normalize dates.

    Args:
        release: An int n >= 1 (n-th distinct value), "latest", or a
            date (str, datetime or pd.Timestamp).

    Returns:
        The release as an int, "latest" or a timezone-naive pd.Timestamp.

    Raises:
        TypeError: If release has an unsupported type.
        ValueError: If release is < 1 or a string that is neither
            "latest" nor a date.
    """

    expected = "release must be an int, 'latest' or a date"

    # bool is an int subclass but True/False are not releases
    if isinstance(release, bool) or not isinstance(release, (Integral, str, datetime)):
        raise TypeError(f"{expected}, got {type(release).__name__}")

    # Integral also accepts numpy ints
    if isinstance(release, Integral):
        if release < 1:
            raise ValueError(
                f"release must be >= 1 (1 = first publication), got {release}"
            )
        return int(release)

    if release == 'latest':
        return release

    # pd.Timestamp also parses words like 'today' or 'now', which change
    # every time the code runs
    if isinstance(release, str) and not release[:1].isdigit():
        raise ValueError(f"{expected}, got {release!r}")

    try:
        release = pd.Timestamp(release)
    except ValueError as err:
        raise ValueError(f"{expected}, got {release!r}") from err

    # Stored dates are naive, so drop the timezone to compare them
    if release.tz is not None:
        release = release.tz_localize(None)

    return release


@dataclass(kw_only=True)
class MacroSeries:
    """Single version of a macroeconomic time series plus its metadata.

    Wraps a numeric pd.Series indexed by date (reference period) and
    computes basic summary statistics on creation.

    Attributes:
        data: Values indexed by a pd.DatetimeIndex, sorted ascending.
            An index of date strings is converted.
        series_id: Identifier in the source (e.g. "UNRATE" in FRED).
        name: Human-readable name of the series.
        source: Data provider (e.g. "FRED").
        frequency: Observation frequency as a Frequency (its value,
            e.g. "M", is also accepted).
        unit: Unit of the values (e.g. "%").
        country: ISO 3166 country code.
        category: Optional user-defined label.
        release: Which version of the data. An int n is the n-th
            distinct value of each period (1 = first publication,
            2 = first revision that changed it, and so on), "latest"
            the most recent version, and a pd.Timestamp the latest
            version published up to that date. Dates are stored as
            timezone-naive pd.Timestamp.
        seasonally_adjusted: True if seasonally adjusted, False if
            not, None if the source does not say.
        mean, std: Computed from data, ignoring NaN.
        start, end: First and last dates with a non-null value.
        n_obs: Number of non-null observations.

    Raises:
        TypeError: If data is not a pd.Series or release has an
            unsupported type.
        ValueError: If the index does not contain unique dates, data is
            empty, all NaN, not numeric (bool included), or frequency or
            release are not valid.
    """

    data: pd.Series = field(repr=False, compare=False)
    series_id: str
    name: str
    source: str
    frequency: Frequency
    unit: str
    country: str
    category: str | None = None  # TODO: consider whether to remove it
    release: int | str | pd.Timestamp = 'latest'
    seasonally_adjusted: bool | None = None
    mean: float = field(init=False)
    std: float = field(init=False)
    start: pd.Timestamp = field(init=False)
    end: pd.Timestamp = field(init=False)
    n_obs: int = field(init=False)

    def __post_init__(self) -> None:
        """Validate data and metadata, then compute summary statistics."""

        valid = [f.value for f in Frequency]
        try:
            self.frequency = Frequency(self.frequency)
        except ValueError as err:
            raise ValueError(
                f"frequency must be one of {valid}, got {self.frequency!r}"
            ) from err

        self.release = parse_release(self.release)

        if not isinstance(self.data, pd.Series):
            raise TypeError(f"data must be a Series, got {type(self.data).__name__}")

        if not isinstance(self.data.index, pd.DatetimeIndex):
            not_dates = f"index must contain dates, got dtype {self.data.index.dtype}"
            if not is_string_dtype(self.data.index):
                raise ValueError(not_dates)
            try:
                index = pd.to_datetime(self.data.index, format='ISO8601')
            except ValueError as err:
                raise ValueError(not_dates) from err
            self.data = self.data.set_axis(index)

        if self.data.index.hasnans:
            raise ValueError("index must not contain missing dates, got NaT")

        if self.data.index.has_duplicates:
            n_dupes = self.data.index.duplicated().sum()
            raise ValueError(f"index must have unique dates, got {n_dupes} duplicates")

        if self.data.empty:
            raise ValueError("data must not be empty, got 0 rows")

        if is_bool_dtype(self.data) or not is_numeric_dtype(self.data):
            raise ValueError(f"data values must be numeric, got dtype {self.data.dtype}")

        if self.data.count() == 0:
            raise ValueError("data must have a non-null value, got only NaN")
        
        self.data = self.data.sort_index()

        self.mean = float(self.data.mean())

        # std is the sample std (n-1)
        self.std = float(self.data.std())

        # Skip leading/trailing NaN so start/end agree with n_obs
        self.start = self.data.first_valid_index()
        self.end = self.data.last_valid_index()

        # count() ignores NaN
        self.n_obs = int(self.data.count())