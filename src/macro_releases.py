from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from macro_series import MacroSeries


@dataclass(kw_only=True)
class MacroReleases:
    """All published versions of a macroeconomic series.

    Stores every value as it was published, so the series can be rebuilt as
    first published, as last revised, or as known on any past date.

    Attributes:
        data: Long DataFrame with columns date (reference period),
            release_date (publication date) and value. Stored sorted
            and indexed by date. Dates given as strings are converted.
        series_id, name, source, frequency, unit, country, category:
            Metadata passed on to every MacroSeries it returns.

    Raises:
        TypeError: If data is not a pd.DataFrame.
        ValueError: If columns are missing, data is empty, value is not
            numeric or dates cannot be parsed.
    """

    data: pd.DataFrame = field(repr=False, compare=False)
    series_id: str
    name: str
    source: str
    frequency: str
    unit: str
    country: str
    category: str # TODO: replace with an Enum once categories are fixed

    def __post_init__(self) -> None:
        """Validate data, parse dates and sort by period."""

        if not isinstance(self.data, pd.DataFrame):
            raise TypeError(
                f"data must be a DataFrame, got {type(self.data).__name__}"
            )

        self.data = self.data.copy()

        required = {'date', 'release_date', 'value'}
        missing = required - set(self.data.columns)
        if missing:
            raise ValueError(f"data is missing columns: {sorted(missing)}")
        
        if self.data.empty:
            raise ValueError("data cannot be empty")

        if not is_numeric_dtype(self.data['value']):
            raise ValueError(
                f"data values must be numeric, got dtype {self.data['value'].dtype}"
            )

        for c in ['date', 'release_date']:
            if not is_datetime64_any_dtype(self.data[c]):
                try:
                    self.data[c] = pd.to_datetime(self.data[c], format='ISO8601')
                except ValueError as err:
                    raise ValueError(
                        f"{c} must contain dates, got dtype {self.data[c].dtype}"
                    ) from err
                
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
        )

    def get_release(self, release: int | str | datetime) -> MacroSeries:
        """Return one version of the series as a MacroSeries.

        Args:
            release: An int n for the n-th release of each period
                (1 = first publication; periods with fewer versions are
                left out), "latest" for the most recent value, or a date
                (str, datetime or pd.Timestamp) for the latest value
                published on or before it.

        Raises:
            TypeError: If release has an unsupported type.
            ValueError: If release is < 1, an unknown string, or no data
                matches.
        """

        if isinstance(release, bool) or not isinstance(release, (int, str, datetime)):
            raise TypeError(
                f"release must be an int, 'latest' or a date, got {type(release).__name__}"
            )
        
        if isinstance(release, int):
            if release < 1:
                raise ValueError(
                    f"release must be >= 1 (1 = first publication), got {release}"
                )
            
            # nth counts from 0, release counts from 1
            return self._to_series(self.data.groupby(level=0)['value'].nth(release - 1), release)

        if release == 'latest':
            return self._to_series(self.data.groupby(level=0)['value'].last(), release)

        try:
            release = pd.Timestamp(release)
        except ValueError as err:
            raise ValueError(
                f"release must be an int, 'latest' or a date, got {release!r}"
            ) from err

        mask = self.data['release_date'] <= release
        return self._to_series(self.data[mask].groupby(level=0)['value'].last(), release)