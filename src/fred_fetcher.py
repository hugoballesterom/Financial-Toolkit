import os
from datetime import datetime
from typing import ClassVar

import pandas as pd
from dotenv import load_dotenv
from fredapi import Fred

from enums import Frequency
from macro_releases import MacroReleases
from macro_series import MacroSeries


class FREDFetcher:
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
            raise ValueError("FRED API key not found: set FRED_API_KEY in .env")
        
        self._fred = Fred(api_key=api_key)

    def _metadata(self, series_id: str, country: str, category: str | None) -> dict:
        """Fetch series info from FRED and map it to MacroSeries fields."""

        info = self._fred.get_series_info(series_id)

        frequency_code = info.get('frequency_short')
        frequency = self.FREQUENCY_MAP.get(frequency_code)

        if frequency is None:
            raise ValueError(
                f"unsupported FRED frequency {frequency_code!r} for series {series_id}"
            )

        return {
            'series_id': series_id,
            'name': info.get('title'),
            'source': 'FRED',
            'frequency': frequency,
            'unit': info.get('units_short'),
            'seasonally_adjusted': 
                self.SEASONAL_ADJUSTMENT_MAP.get(info.get('seasonal_adjustment_short')),
            'country': country,
            'category': category,
        }

    def get_macro_series(
        self,
        series_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        country: str = 'US',
        category: str | None = None,  # TODO: consider whether to remove it
    ) -> MacroSeries:
        """Download the current (latest revised) values of a series.

        Args:
            series_id: FRED identifier, e.g. 'UNRATE'.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED does not provide it, so it
                defaults to 'US'.
            category: Optional user-defined label.

        Raises:
            ValueError: If FRED reports a frequency not in Frequency.
        """
        
        data = self._fred.get_series(
            series_id=series_id,
            observation_start=start,
            observation_end=end,
        )
        
        return MacroSeries(
            data=data,
            **self._metadata(series_id=series_id, country=country, category=category),
        )

    def get_macro_releases(
        self,
        series_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        country: str = 'US',
        category: str | None = None,  # TODO: consider whether to remove it
    ) -> MacroReleases:
        """Download every published version of a series from ALFRED.

        Args:
            series_id: FRED identifier, e.g. 'UNRATE'.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. FRED does not provide it, so it
                defaults to 'US'.
            category: Optional user-defined label.

        Raises:
            ValueError: If FRED reports a frequency not in Frequency.
        """
        
        data = self._fred.get_series_all_releases(series_id=series_id)
        data = data.rename(columns={'realtime_start': 'release_date'})

        # ALFRED marks missing vintages as "."; fredapi stores them as NaN, but its
            # transposed DataFrame turns them into NaT.
        data['value'] = pd.to_numeric(data['value'], errors='coerce')
        data['date'] = pd.to_datetime(data['date'])
        data['release_date'] = pd.to_datetime(data['release_date'])

        if start is not None:
            data = data[data['date'] >= pd.Timestamp(start)]
        if end is not None:
            data = data[data['date'] <= pd.Timestamp(end)]

        return MacroReleases(
            data=data,
            **self._metadata(series_id=series_id, country=country, category=category),
        )