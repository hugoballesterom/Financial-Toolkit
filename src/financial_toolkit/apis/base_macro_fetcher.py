import os
import time
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, ClassVar

from ..models.macro_releases import MacroReleases
from ..models.macro_series import MacroSeries


class BaseMacroFetcher(ABC):
    """Common interface of the macroeconomic data sources.

    Subclasses implement get_macro_series and, if the source publishes past
    versions, get_macro_releases. _fetch_many and _with_retry know nothing
    about macro data, so they can move to a shared parent class as they are.

    Attributes:
        MAX_ATTEMPTS: Times a request is tried before giving up.
        BACKOFF_SECONDS: Seconds to wait after the first failed attempt. The
            wait doubles after each further failure.
    """

    MAX_ATTEMPTS: ClassVar[int] = 3
    BACKOFF_SECONDS: ClassVar[float] = 1.0

    @abstractmethod
    def get_macro_series(
        self,
        series_id: str,
        *,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,
    ) -> MacroSeries:
        """Download the current values of a series.

        Args:
            series_id: Identifier of the series in the source.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. Each source decides what None means.
            category: Optional user-defined label.
        """

    def get_macro_releases(
        self,
        series_id: str,
        *,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        country: str | None = None,
        category: str | None = None,
    ) -> MacroReleases:
        """Download every published version of a series.

        Args:
            series_id: Identifier of the series in the source.
            start, end: Optional limits on the reference period.
            country: ISO 3166 code. Each source decides what None means.
            category: Optional user-defined label.

        Raises:
            NotImplementedError: If the source does not publish past versions.
        """

        raise NotImplementedError(
            f"source must publish past versions to use get_macro_releases, "
            f"got {type(self).__name__}"
        )

    def get_many_macro_series(
        self,
        series_ids: Iterable[str],
        **kwargs: Any,
    ) -> dict[str, MacroSeries]:
        """Download several series, skipping the ones that fail.

        Args:
            series_ids: Identifiers of the series in the source.
            **kwargs: Passed to get_macro_series for every series.

        Returns:
            The downloaded series by identifier. Failed ones are left out and
            reported in a single warning.

        Raises:
            TypeError: If series_ids is a single string or a keyword argument
                is not valid.
        """

        return self._fetch_many(self.get_macro_series, series_ids, **kwargs)

    def _fetch_many(
        self,
        fetch: Callable[..., Any],
        ids: Iterable[str],
        /,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call fetch for each id and warn once about the ones that fail.

        Only errors about the data or the connection are collected, so that
        programming errors such as a misspelled keyword still raise.

        Args:
            fetch: Function that takes an id and the keyword arguments.
            ids: Identifiers to fetch.
            **kwargs: Passed to fetch for every id.

        Returns:
            The result of each successful call by id.

        Raises:
            TypeError: If ids is a single string.
        """

        # A string is iterable, so 'UNRATE' would be fetched letter by letter
        if isinstance(ids, str):
            raise TypeError(f"ids must be a collection of ids, got str {ids!r}")

        results = {}
        failed = {}

        for id_ in ids:
            try:
                results[id_] = fetch(id_, **kwargs)
            except (ValueError, ConnectionError) as err:
                failed[id_] = f"{type(err).__name__}: {err}"

        if failed:
            reasons = "; ".join(f"{id_!r} ({why})" for id_, why in failed.items())
            warnings.warn(
                f"{len(failed)} of {len(failed) + len(results)} ids failed: {reasons}",
                skip_file_prefixes=(os.path.dirname(os.path.dirname(__file__)),),
            )

        return results

    def _with_retry(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call func, trying again if the connection fails.

        func must raise the built-in ConnectionError: requests.ConnectionError
        does not inherit from it, so library errors must be translated first.

        Args:
            func: Function that makes one attempt.
            *args, **kwargs: Passed to func on every attempt.

        Returns:
            What func returns on the first attempt that succeeds.

        Raises:
            ConnectionError: The last error, if every attempt fails.
        """

        for attempt in range(self.MAX_ATTEMPTS):
            try:
                return func(*args, **kwargs)

            except ConnectionError:
                if attempt == self.MAX_ATTEMPTS - 1:
                    raise
                time.sleep(self.BACKOFF_SECONDS * 2 ** attempt)
