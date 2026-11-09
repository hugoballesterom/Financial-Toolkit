import os
from dataclasses import dataclass, field, replace

import pandas as pd

from ..apis.YahooFinanceAPI import YahooFinanceAPI
from ..apis.fmp_api import FMPAPI
from ..apis.coingeckoapi import CoinGeckoApi
from ..apis.us_treasury_api import USTreasuryAPI
from ..apis.bce_bond_api import BCEBondAPI
from ..apis.jp_bond_api import JapanBondAPI
from ..apis.uk_bond_api import UKBondAPI
from .bond_normalizer import BondNormalizer
from .cleaning import clean_prices


@dataclass
class AssetFetcher:
    yahoo: YahooFinanceAPI = field(default_factory=YahooFinanceAPI)

    fmp: FMPAPI = field(
        default_factory=lambda: FMPAPI(
            api_key=os.getenv("FMP_API_KEY") or ""
        )
    )

    coingecko: CoinGeckoApi = field(default_factory=CoinGeckoApi)

    us_treasury: USTreasuryAPI = field(default_factory=USTreasuryAPI)
    bce: BCEBondAPI = field(default_factory=BCEBondAPI)
    japan: JapanBondAPI = field(default_factory=JapanBondAPI)
    uk: UKBondAPI = field(default_factory=UKBondAPI)

    bond_normalizer: BondNormalizer = field(
        default_factory=BondNormalizer
    )

    # Cleaning report of the last call to get_many, by symbol.
    cleaning_reports: dict = field(default_factory=dict, init=False)

    def get_many(self, requests, *, start, end):
        """receives the list, picks the fetcher of each asset and gathers the results. This is the behaviour we want from AssetFetcher."""
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

        if (
            pd.isna(start)
            or pd.isna(end)
            or start.tzinfo is not None
            or end.tzinfo is not None
        ):
            raise ValueError("Use valid dates without a timezone")

        start = start.normalize()
        end = end.normalize()

        if start > end or end > today:
            raise ValueError(
                "start must be <= end and end cannot be in the future"
            )

        fetchers = {
            ("stock", "yfinance"): self.yahoo.get_stock,
            ("index", "yfinance"): self.yahoo.get_index,
            ("stock", "fmp"): self.fmp.get_stock,
            ("index", "fmp"): self.fmp.get_index,
            ("crypto", "yfinance"): self.yahoo.get_crypto,
            ("crypto", "coingecko"): self.coingecko.get_crypto,
            ("bond", "us_treasury"): self.us_treasury.get_data,
            ("bond", "bce"): self.bce.get_data,
            ("bond", "japan"): self.japan.get_data,
            ("bond", "uk"): self.uk.get_data,
        }

        assets = []
        self.cleaning_reports = {}

        for request in requests:
            kind = request["type"].strip().lower()
            api = request["api"].strip().lower()
            symbol = request["symbol"].strip()
            key = (kind, api)

            if key not in fetchers:
                raise ValueError(f"Unsupported combination: {key}")

            if api == "fmp" and not self.fmp.api_key:
                raise ValueError("FMP_API_KEY is missing")

            parameters = self._parameters(
                kind, api, symbol, start, end, today
            )

            options = request.get("params", {})
            if not isinstance(options, dict):
                raise ValueError("params must be a dictionary")

            reserved = {
                "start", "end", "start_date", "end_date",
                "period", "days", "ticker", "symbol", "coin_id",
            }

            if reserved.intersection(options):
                raise ValueError(
                    "Give the asset in symbol and the period "
                    "in start/end of get_many()"
                )

            asset = fetchers[key](**parameters, **options)

            if kind == "bond":
                asset = self.bond_normalizer.normalize(
                    data=asset,
                    ticker=symbol,
                    source=api,
                    start_date=start,
                    end_date=end,
                )
            else:
                asset = self._trim(asset, start, end)
                prices, report = clean_prices(asset.price)
                asset = replace(asset, price=prices)
                self.cleaning_reports[symbol] = report

            assets.append(asset)

        return assets

    @staticmethod
    def _parameters(kind, api, symbol, start, end, today):
        """translates the dates because our fetchers use different arguments: period, start/end or days."""
        if kind == "bond":
            return {
                "ticker": symbol,
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
            }

        if api == "coingecko":
            needed = (today - start).days + 1

            days = next(
                (
                    window
                    for window in (1, 7, 14, 30, 90, 180, 365)
                    if window >= needed
                ),
                None,
            )

            if days is None:
                raise ValueError(
                    "The current CoinGecko fetcher does not cover "
                    "the requested start"
                )

            return {"coin_id": symbol, "days": days}

        if api == "yfinance" and kind == "index":
            return {
                "symbol": symbol,
                "start": start.strftime("%Y-%m-%d"),
                # Yahoo treats end as exclusive.
                "end": (
                    end + pd.Timedelta(days=1)
                ).strftime("%Y-%m-%d"),
            }

        # The remaining methods take a period in years.
        years = max(1, today.year - start.year + 1)
        identifier = "ticker" if kind == "stock" else "symbol"

        return {
            identifier: symbol,
            "period": f"{years}y",
        }

    @staticmethod
    def _trim(asset, start, end):
        """limits the prices to the chosen interval, because some fetchers download a wider period."""
        prices = asset.price
        index = pd.DatetimeIndex(prices.close.index)
        dates = index.tz_localize(None).normalize()
        selection = (dates >= start) & (dates <= end)

        if not selection.any():
            raise ValueError(
                "No prices within the requested period"
            )

        columns = {
            name: (
                None
                if getattr(prices, name) is None
                else getattr(prices, name).iloc[selection].copy()
            )
            for name in ("open", "high", "low", "close", "volume")
        }

        trimmed_prices = replace(
            prices,
            date=index[selection],
            **columns,
        )

        return replace(asset, price=trimmed_prices)