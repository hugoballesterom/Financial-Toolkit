from ..models.cryptocurrency import Cryptocurrency
from dataclasses import dataclass, field
import os
import requests
from ..models.priceseries import PriceSeries
from ..models.tokenomics import Tokenomics
import pandas as pd

@dataclass
class CoinGeckoApi:
    api_key: str = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY")
    )
    def get_crypto(self, coin_id, currency="usd", days=30):
        base_url="https://api.coingecko.com/api/v3"
        if not self.api_key:
            raise ValueError("COINGECKO_API_KEY is not configured")
        params={"vs_currency": currency, "ids": coin_id}
        headers={"x-cg-demo-api-key":self.api_key}
        response=requests.get(
            f"{base_url}/coins/markets",
            headers=headers,
            params=params,
            timeout=15
        )
        response.raise_for_status()

        data=response.json()
        assert data, f"The cryptocurrency {coin_id} has not been found"
        crypto_data = data[0]
        tokenomics = Tokenomics(
            circulating_supply=crypto_data.get("circulating_supply"),
            total_supply=crypto_data.get("total_supply"),
            max_supply=crypto_data.get("max_supply")
        )

        params={"vs_currency": currency, "days": days}
        response2=requests.get(
            f"{base_url}/coins/{coin_id}/ohlc",
            headers=headers,
            params=params,
            timeout=15
        )
        response2.raise_for_status()
        prices_df = pd.DataFrame(response2.json(),columns=["date", "open", "high", "low", "close"])
        if prices_df.empty:
            raise ValueError(f"No OHLC data found for {coin_id}")
        prices_df["date"] = pd.to_datetime(prices_df["date"], unit="ms", utc=True)
        prices_df = (prices_df.sort_values("date").set_index("date"))

        priceser=PriceSeries(
            date=prices_df.index,
            open=prices_df["open"],
            high=prices_df["high"],
            low=prices_df["low"],
            close=prices_df["close"],
            volume=None)


        response3 = requests.get(
            f"{base_url}/coins/{coin_id}",
            headers=headers,
            params={
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false"
            },
            timeout=15
            )

        response3.raise_for_status()

        coin_info = response3.json()

        blockchains = list(coin_info.get("platforms", {}).keys())

        crypto = Cryptocurrency(
            name=crypto_data["name"],
            symbol=crypto_data["symbol"],
            blockchain=blockchains,
            price=priceser,
            market_cap=crypto_data.get("market_cap"),
            market_cap_rank=crypto_data.get("market_cap_rank"),
            tokenomics=tokenomics
        )
        return crypto





    
