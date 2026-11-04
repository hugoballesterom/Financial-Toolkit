from collections.abc import Iterable
from datetime import datetime
from typing import ClassVar

from models.base_macro_fetcher import BaseMacroFetcher
from models.fred_fetcher import FREDFetcher
from models.macro_releases import MacroReleases
from models.macro_series import MacroSeries
from models.wb_fetcher import WorldBankFetcher


class MacroFetcher:
    """Single entry point to the macroeconomic data sources.

    Sends each request to the fetcher of its source. A fetcher is created the
    first time its source is requested and then reused, so FRED_API_KEY (read
    from the environment or .env) is only needed to use FRED.

    Attributes:
        SOURCES: Fetcher class of each accepted source name, in lowercase.
    """

    SOURCES: ClassVar[dict[str, type[BaseMacroFetcher]]] = {
        'fred': FREDFetcher,
        'wb': WorldBankFetcher,
        'world bank': WorldBankFetcher,
        'worldbank': WorldBankFetcher,
        'world_bank': WorldBankFetcher,
    }

    def __init__(self) -> None:
        """Create the entry point. No fetcher is created yet."""

        self._fetchers: dict[type[BaseMacroFetcher], BaseMacroFetcher] = {}

    def _fetcher(self, source: str) -> BaseMacroFetcher:
        """Return the fetcher of a source, creating it if needed.

        Raises:
            ValueError: If source is not in SOURCES, or FRED is requested and
                FRED_API_KEY is not set.
        """

        name = str(source).strip().lower()

        if name not in self.SOURCES:
            raise ValueError(
                f"source must be one of {list(self.SOURCES)}, got {source!r}"
            )

        fetcher_class = self.SOURCES[name]

        if fetcher_class not in self._fetchers:
            self._fetchers[fetcher_class] = fetcher_class()

        return self._fetchers[fetcher_class]

    def get_macro_series(
        self,
        series_id: str,
        *,
        source: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,
    ) -> MacroSeries:
        """Download the current values of a series.

        Args:
            series_id: Identifier of the series in the source, e.g. 'UNRATE'.
            source: Data source, e.g. 'FRED' or 'WB'. Case does not matter.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED takes None as 'US'; the World Bank
                requires it.
            category: Optional user-defined label.

        Raises:
            ValueError: If source is not valid, FRED_API_KEY is missing, or the
                source rejects the request or has no data for it.
            ConnectionError: If the source cannot be reached or its response
                cannot be read.
        """

        return self._fetcher(source).get_macro_series(
            series_id, start=start, end=end, country=country, category=category
        )

    def get_macro_releases(
        self,
        series_id: str,
        *,
        source: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,
    ) -> MacroReleases:
        """Download every published version of a series.

        Args:
            series_id: Identifier of the series in the source, e.g. 'UNRATE'.
            source: Data source, e.g. 'FRED'. Case does not matter.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED takes None as 'US'.
            category: Optional user-defined label.

        Raises:
            NotImplementedError: If the source does not publish past versions,
                as with the World Bank.
            ValueError: If source is not valid, FRED_API_KEY is missing, or the
                source rejects the request or has no data for it.
            ConnectionError: If the source cannot be reached or its response
                cannot be read.
        """

        return self._fetcher(source).get_macro_releases(
            series_id, start=start, end=end, country=country, category=category
        )

    def get_many_macro_series(
        self,
        series_ids: Iterable[str],
        *,
        source: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,
    ) -> dict[str, MacroSeries]:
        """Download several series from one source, skipping the ones that fail.

        Args:
            series_ids: Identifiers of the series in the source.
            source: Data source, e.g. 'FRED' or 'WB'. Case does not matter.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED takes None as 'US'; the World Bank
                requires it.
            category: Optional user-defined label.

        Returns:
            The downloaded series by identifier. Failed ones are left out and
            reported in a single warning.

        Raises:
            TypeError: If series_ids is a single string.
            ValueError: If source is not valid or FRED_API_KEY is missing.
        """

        return self._fetcher(source).get_many_macro_series(
            series_ids, start=start, end=end, country=country, category=category
        )
