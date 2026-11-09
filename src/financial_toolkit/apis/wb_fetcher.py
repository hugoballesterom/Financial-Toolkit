from datetime import datetime
from typing import Any, ClassVar

import pandas as pd
import requests

from .base_macro_fetcher import BaseMacroFetcher
from ..enums import Frequency
from ..exceptions import RateLimitError
from ..models.macro_series import MacroSeries


class WorldBankFetcher(BaseMacroFetcher):
    """Download macroeconomic data from the World Bank.

    Translates World Bank metadata to the toolkit's standard vocabulary and
    returns MacroSeries. The API only reports the last update of a series, not
    its past versions, so get_macro_releases is not available.
    """

    WB_URL = 'https://api.worldbank.org/v2'

    # Only annual: quarterly series have no metadata and their dates ('2026Q2')
    # are not ISO 8601
    FREQUENCY_MAP: ClassVar[dict[str, Frequency]] = {
        'Annual': Frequency.YEARLY,
    }

    def _get(self, path: str, **params: Any) -> Any:
        """Call the World Bank API, trying again if the connection fails.

        Raises:
            RateLimitError: If the API answers HTTP 429 on every attempt.
            ValueError: If the API rejects the request.
            ConnectionError: If the API cannot be reached or read on any attempt.
        """

        return self._with_retry(self._get_once, path, **params)

    def _get_once(self, path: str, **params: Any) -> Any:
        """Call the World Bank API and turn its errors into toolkit errors.

        The API answers HTTP 200 even when it rejects a request, either with
        a JSON body holding a message or with an XML error.

        Raises:
            RateLimitError: If the API answers HTTP 429 (too many requests).
            ValueError: If the API rejects the request.
            ConnectionError: If the API cannot be reached or its response
                cannot be read.
        """

        try:
            response = requests.get(
                f"{self.WB_URL}/{path}",
                params={'format': 'json', **params},
                timeout=30,
            )

            if response.status_code == 429:
                raise RateLimitError(f"World Bank rate limit exceeded for {path!r}")

            response.raise_for_status()
            body = response.json()

        except requests.JSONDecodeError as err:
            if 'wb:error' in response.text:
                raise ValueError(f"World Bank has no data for {path!r}") from err
            
            raise ConnectionError(
                f"World Bank response must be JSON, got {response.text[:100]!r}"
            ) from err
        
        except requests.RequestException as err:
            raise ConnectionError(
                f"World Bank must be reachable, got {type(err).__name__}: {err}"
            ) from err

        if isinstance(body, list) and body and 'message' in body[0]:
            raise ValueError(
                f"World Bank rejected the request {path!r}: "
                f"{body[0]['message'][0]['value']}"
            )

        return body

    def _metadata(
        self,
        series_id: str,
        source_id: str,
        country: str,
        category: str | None,
    ) -> dict:
        """Fetch series info from the World Bank and map it to MacroSeries fields."""

        try:
            body = self._get(f"sources/{source_id}/series/{series_id}/metadata")

        except ValueError as err:
            raise ValueError(
                f"metadata of {series_id!r} must be available "
                f"(only annual series are supported), got none"
            ) from err

        meta = body['source'][0]['concept'][0]['variable'][0]['metatype']
        info = {m['id']: m['value'] for m in meta}

        frequency_code = info.get('Periodicity')
        frequency = self.FREQUENCY_MAP.get(frequency_code)

        if frequency is None:
            raise ValueError(
                f"frequency of {series_id!r} must be one of "
                f"{list(self.FREQUENCY_MAP)}, got {frequency_code!r}"
            )

        return {
            'series_id': series_id,
            'name': info.get('IndicatorName'),
            'source': 'World Bank',
            'frequency': frequency,
            'unit': info.get('Unitofmeasure'),
            'seasonally_adjusted': None,
            'country': country,
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
        """Download the values of a series for one country.

        Args:
            series_id: World Bank identifier, e.g. 'NY.GDP.MKTP.CD'.
            start, end: Optional limits on the reference period. Each annual
                value is dated January 1, so start='2020-06-01' leaves out 2020.
            country: ISO 3166 code, e.g. 'ES'. Required by this source.
            category: Optional user-defined label.

        Raises:
            ValueError: If country is None, the World Bank rejects the request,
                has no data for the country, reports a frequency not in
                FREQUENCY_MAP, or start/end leave no observations.
            RateLimitError: If the API answers HTTP 429 (too many requests).
                It is a ConnectionError, so catching that also covers it.
            ConnectionError: If the API cannot be reached or its response
                cannot be read.
        """

        if country is None:
            raise ValueError("country must be an ISO 3166 code, got None")

        meta, rows = self._get(
            f"country/{country}/indicator/{series_id}", per_page=20000
        )

        if not rows:
            raise ValueError(
                f"country must have observations of {series_id!r}, got {country!r}"
            )

        metadata = self._metadata(
            series_id=series_id,
            source_id=meta['sourceid'],
            country=country,
            category=category,
        )

        # Repeated dates must reach MacroSeries to be rejected
        data = pd.Series(
            pd.to_numeric([row['value'] for row in rows]),
            index=pd.to_datetime([row['date'] for row in rows], format='ISO8601'),
        )

        if start is not None:
            data = data[data.index >= pd.Timestamp(start)]
        if end is not None:
            data = data[data.index <= pd.Timestamp(end)]

        if data.empty:
            raise ValueError(
                f"start/end must overlap the observations of {series_id!r}, "
                f"got start={start} and end={end}"
            )

        return MacroSeries(data=data, **metadata)
