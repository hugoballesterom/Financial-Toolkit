import os
from collections.abc import Callable
from datetime import datetime
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from xml.etree.ElementTree import ParseError

import pandas as pd
from dotenv import load_dotenv
from fredapi import Fred

from models.base_macro_fetcher import BaseMacroFetcher
from models.enums import Frequency
from models.exceptions import RateLimitError
from models.macro_releases import MacroReleases
from models.macro_series import MacroSeries


class FREDFetcher(BaseMacroFetcher):
    """Download macroeconomic data from FRED and ALFRED.

    Translates FRED metadata to the toolkit's standard vocabulary and
    returns MacroSeries (current data) or MacroReleases (all vintages).
    The API key is read from FRED_API_KEY (.env) unless passed.
    """

    FREQUENCY_MAP: ClassVar[dict[str, Frequency]] = {
        'D': Frequency.DAILY,
        'W': Frequency.WEEKLY,
        'BW': Frequency.BIWEEKLY,
        'M': Frequency.MONTHLY,
        'Q': Frequency.QUARTERLY,
        'SA': Frequency.SEMIANNUAL,
        'A': Frequency.YEARLY,
    }

    SEASONAL_ADJUSTMENT_MAP: ClassVar[dict[str, bool]] = {
        'SA': True,
        'SAAR': True,
        'SSA': True,
        'NSA': False,
    }

    def __init__(self, api_key: str | None = None) -> None:
        """Create the FRED client.

        Raises:
            ValueError: If no API key is given or found in the environment.
        """

        load_dotenv()
        api_key = api_key or os.getenv('FRED_API_KEY')

        if not api_key:
            raise ValueError("FRED_API_KEY must be set in .env, got none")

        self._fred = Fred(api_key=api_key)

    def _call(self, method: Callable[..., Any], series_id: str, **kwargs: Any) -> Any:
        """Call a fredapi method, trying again if the connection fails.

        Raises:
            RateLimitError: If FRED answers HTTP 429 on every attempt.
            ValueError: If FRED rejects the request or has no data for it.
            ConnectionError: If FRED cannot be reached or read on any attempt.
        """

        return self._with_retry(self._call_once, method, series_id, **kwargs)

    def _call_once(
        self, method: Callable[..., Any], series_id: str, **kwargs: Any
    ) -> Any:
        """Call a fredapi method and turn its errors into toolkit errors.

        fredapi turns HTTP errors (unknown series, invalid API key, too many
        requests) into ValueError with FRED's message (or ParseError if the
        body is not XML), raised inside its except block, so the original
        HTTPError is kept in __context__.

        Raises:
            RateLimitError: If FRED answers HTTP 429 (too many requests).
            ValueError: If FRED rejects the request or has no data for it.
            ConnectionError: If FRED cannot be reached or its response
                cannot be read.
        """

        try:
            return method(series_id, **kwargs)
        except (ValueError, ParseError) as err:
            http_error = err.__context__
            if isinstance(http_error, HTTPError) and http_error.code == 429:
                raise RateLimitError(
                    f"FRED rate limit exceeded for {series_id!r}: {err}"
                ) from err
            if isinstance(err, ParseError):
                raise ConnectionError(
                    f"FRED response must be readable XML, got {err}"
                ) from err
            raise ValueError(f"FRED rejected the request for {series_id!r}: {err}") from err
        except URLError as err:
            raise ConnectionError(
                f"FRED must be reachable, got {type(err).__name__}: {err}"
            ) from err

    def _metadata(
        self, series_id: str, country: str | None, category: str | None
    ) -> dict:
        """Fetch series info from FRED and map it to MacroSeries fields."""

        info = self._call(self._fred.get_series_info, series_id)

        frequency_code = info.get('frequency_short')
        frequency = self.FREQUENCY_MAP.get(frequency_code)

        if frequency is None:
            raise ValueError(
                f"frequency of {series_id!r} must be one of "
                f"{list(self.FREQUENCY_MAP)}, got {frequency_code!r}"
            )

        seasonally_adjusted = self.SEASONAL_ADJUSTMENT_MAP.get(info.get('seasonal_adjustment_short'))
        return {
            'series_id': series_id,
            'name': info.get('title'),
            'source': 'FRED',
            'frequency': frequency,
            'unit': info.get('units_short'),
            'seasonally_adjusted': seasonally_adjusted,
            'country': 'US' if country is None else country,
            'category': category,
        }

    def get_macro_series(
        self,
        series_id: str,
        *,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,  # TODO: consider whether to remove it
    ) -> MacroSeries:
        """Download the current (latest revised) values of a series.

        Args:
            series_id: FRED identifier, e.g. 'UNRATE'.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED does not provide it, so None
                becomes 'US'.
            category: Optional user-defined label.

        Raises:
            ValueError: If FRED rejects the request, reports a frequency
                not in Frequency, or start/end leave no observations.
            RateLimitError: If FRED answers HTTP 429 (too many requests).
                It is a ConnectionError, so catching that also covers it.
            ConnectionError: If FRED cannot be reached or its response
                cannot be read.
        """

        metadata = self._metadata(
            series_id=series_id, country=country, category=category
        )

        data = self._call(
            self._fred.get_series,
            series_id,
            observation_start=start,
            observation_end=end,
        )

        if data.empty:
            raise ValueError(
                f"start/end must overlap the observations of {series_id!r}, "
                f"got start={start} and end={end}"
            )

        return MacroSeries(data=data, **metadata)

    def get_macro_releases(
        self,
        series_id: str,
        *,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,  # TODO: consider whether to remove it
    ) -> MacroReleases:
        """Download every published version of a series from ALFRED.

        Args:
            series_id: FRED identifier, e.g. 'UNRATE'.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED does not provide it, so None
                becomes 'US'.
            category: Optional user-defined label.

        Raises:
            ValueError: If FRED rejects the request, reports a frequency
                not in Frequency, or start/end leave no periods.
            RateLimitError: If FRED answers HTTP 429 (too many requests).
                It is a ConnectionError, so catching that also covers it.
            ConnectionError: If FRED cannot be reached or its response
                cannot be read.
        """

        metadata = self._metadata(
            series_id=series_id, country=country, category=category
        )

        data = self._call(self._fred.get_series_all_releases, series_id)
        data = data.rename(columns={'realtime_start': 'release_date'})

        # ALFRED marks missing vintages as "."; fredapi stores them as NaN, but its
        # transposed DataFrame turns them into NaT.
        data['value'] = pd.to_numeric(data['value'], errors='coerce')
        data['date'] = pd.to_datetime(data['date'])
        data['release_date'] = pd.to_datetime(data['release_date'])

        first, last = data['date'].min(), data['date'].max()

        if start is not None:
            data = data[data['date'] >= pd.Timestamp(start)]
        if end is not None:
            data = data[data['date'] <= pd.Timestamp(end)]

        if data.empty:
            raise ValueError(
                f"start/end must overlap the periods {first.date()} to "
                f"{last.date()} of {series_id!r}, got start={start} and end={end}"
            )

        return MacroReleases(data=data, **metadata)