from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
    is_string_dtype,
)

from ..enums import Frequency
from .macro_series import MacroSeries, parse_release


@dataclass(kw_only=True)
class MacroReleases:
    """All published versions of a macroeconomic series.

    Stores every value as it was published, so the series can be rebuilt as
    first published, as last revised, or as known on any past date.

    Attributes:
        data: Long DataFrame with columns date (reference period),
            release_date (publication date) and value. Stored sorted
            and indexed by date. Dates given as strings are converted.
        series_id, name, source, frequency, unit, country, category,
            seasonally_adjusted: Metadata passed on to every MacroSeries
            it returns.

    Raises:
        TypeError: If data is not a pd.DataFrame.
        ValueError: If columns are missing, data is empty, value is not
            numeric (bool included), dates cannot be parsed or are
            missing (NaT), a (date, release_date) pair is repeated, or
            frequency is not a valid Frequency.
    """

    data: pd.DataFrame = field(repr=False, compare=False)
    series_id: str
    name: str
    source: str
    frequency: Frequency
    unit: str | None
    country: str
    category: str | None = None  # TODO: consider whether to remove it
    seasonally_adjusted: bool | None = None

    def __post_init__(self) -> None:
        """Validate data, parse dates and sort by period."""

        valid = [f.value for f in Frequency]
        try:
            self.frequency = Frequency(self.frequency)
        except ValueError as err:
            raise ValueError(
                f"frequency must be one of {valid}, got {self.frequency!r}"
            ) from err

        if not isinstance(self.data, pd.DataFrame):
            raise TypeError(
                f"data must be a DataFrame, got {type(self.data).__name__}"
            )

        self.data = self.data.copy()

        required = {'date', 'release_date', 'value'}
        missing = required - set(self.data.columns)
        if missing:
            raise ValueError(
                f"data must have columns {sorted(required)}, "
                f"got {sorted(self.data.columns)}"
            )

        if self.data.empty:
            raise ValueError("data must not be empty, got 0 rows")

        value_dtype = self.data['value'].dtype
        if is_bool_dtype(value_dtype) or not is_numeric_dtype(value_dtype):
            raise ValueError(f"data values must be numeric, got dtype {value_dtype}")

        for c in ['date', 'release_date']:
            if not is_datetime64_any_dtype(self.data[c]):
                not_dates = f"{c} must contain dates, got dtype {self.data[c].dtype}"
                if not is_string_dtype(self.data[c]):
                    raise ValueError(not_dates)
                try:
                    self.data[c] = pd.to_datetime(self.data[c], format='ISO8601')
                except ValueError as err:
                    raise ValueError(not_dates) from err

            # groupby drops NaT dates and NaT release dates break the ordering
            n_missing = self.data[c].isna().sum()
            if n_missing:
                raise ValueError(f"{c} must not contain NaT, got {n_missing}")

        # A repeated pair makes the n-th and latest value ambiguous
        n_dupes = self.data.duplicated(subset=['date', 'release_date']).sum()
        if n_dupes:
            raise ValueError(
                f"(date, release_date) pairs must be unique, got {n_dupes} duplicates"
            )

        self.data = self.data.sort_values(by=['date', 'release_date']).set_index('date')

    def _to_series(self, data: pd.Series, release: int | str | pd.Timestamp) -> MacroSeries:
        """Wrap a single version in a MacroSeries with this object's metadata."""

        return MacroSeries(
            data=data,
            series_id=self.series_id,
            name=self.name,
            source=self.source,
            frequency=self.frequency,
            unit=self.unit,
            country=self.country,
            category=self.category,
            release=release,
            seasonally_adjusted=self.seasonally_adjusted,
        )

    def get_release(self, release: int | str | datetime) -> MacroSeries:
        """Return one version of the series as a MacroSeries.

        Args:
            release: An int n for the n-th distinct value of each period
                (1 = first publication, 2 = first revision that changed
                it, and so on; periods with fewer distinct values are
                left out), "latest" for the most recent value, or a date
                (str, datetime or pd.Timestamp) for the latest value
                published on or before it. Timezones are dropped.

        Raises:
            TypeError: If release has an unsupported type.
            ValueError: If release is < 1, a string that is neither
                "latest" nor a date, greater than the most distinct
                values of any period, or before the first release_date.
        """

        release = parse_release(release)
        by_period = self.data.groupby(level=0)['value']

        if isinstance(release, int):
            max_release = by_period.size().max()
            if release > max_release:
                raise ValueError(
                    f"release must be <= {max_release} (most versions of any "
                    f"period), got {release}"
                )

            # nth counts from 0, release counts from 1
            return self._to_series(by_period.nth(release - 1), release)

        if release == 'latest':
            return self._to_series(by_period.nth(-1), release)

        first_release = self.data['release_date'].min()
        if release < first_release:
            raise ValueError(
                f"release must be on or after the first release_date "
                f"{first_release.date()}, got {release.date()}"
            )

        mask = self.data['release_date'] <= release
        return self._to_series(
            self.data[mask].groupby(level=0)['value'].nth(-1), release
        )