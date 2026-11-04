from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import requests

from priceseries import PriceSeries
from stock import Stock
from company import Company
from fundamentals import Fundamentals
from income_statement import IncomeStatement
from income_statement_history import IncomeStatementHistory
from balance_sheet import BalanceSheet
from balance_sheet_history import BalanceSheetHistory
from cashflow import CashFlow
from cashflow_history import CashFlowHistory
from index import Index

income = [
    "revenue",
    "costOfRevenue",
    "grossProfit",
    "operatingExpenses",
    "operatingIncome",
    "interestExpense",
    "incomeBeforeTax",
    "incomeTaxExpense",
    "netIncome"
]

balance = [
    "cashAndShortTermInvestments",
    "totalDebt",
    "accountsReceivables",
    "inventory",
    "totalCurrentAssets",
    "propertyPlantEquipmentNet",
    "goodwillAndIntangibleAssets",
    "totalAssets",
    "totalCurrentLiabilities",
    "longTermDebt",
    "totalLiabilities",
    "totalStockholdersEquity"
]

cashflow = [
    "netIncome",
    "depreciationAndAmortization",
    "changeInWorkingCapital",
    "netCashProvidedByOperatingActivities",
    "capitalExpenditure",
    "netCashProvidedByInvestingActivities",
    "debtIssuance",
    "debtRepayment",
    "commonStockRepurchased",
    "commonDividendsPaid",
    "netCashProvidedByFinancingActivities",
    "netChangeInCash"
]


@dataclass
class FMPAPI:

    api_key: str

    def get_stock(
        self,
        ticker: str,
        period: str = "5y",
        interval: str = "1d"
    ) -> Stock:

        assert len(ticker) > 0, "The ticker must not be empty"
        assert interval == "1d", "FMPAPI currently supports only daily prices"

        symbol = ticker.upper()

        url = "https://financialmodelingprep.com/stable/"

        params = {
            "symbol": symbol,
            "apikey": self.api_key
        }

        # Historical prices

        today = date.today()

        if period == "max":
            start = date(1900, 1, 1)
        else:
            assert period.endswith("y"), "Use periods such as 1y, 5y, 10y or max"
            years = int(period[:-1])
            start = today - timedelta(days=365 * years + 5)

        price_params = {
            **params,
            "from": start.isoformat(),
            "to": today.isoformat()
        }

        response = requests.get(
            url + "historical-price-eod/full",
            params=price_params,
            timeout=30
        )

        if response.status_code == 402:
            raise ValueError(
                f"Historical prices for {ticker} require a paid FMP subscription"
            )

        response.raise_for_status()

        prices_df = pd.DataFrame(response.json())

        assert not prices_df.empty, f"The ticker {ticker} has not been found"

        prices_df["date"] = pd.to_datetime(prices_df["date"])

        prices_df = prices_df.sort_values("date").set_index("date")

        prices = PriceSeries(
            date=prices_df.index,
            open=prices_df["open"],
            high=prices_df["high"],
            low=prices_df["low"],
            close=prices_df["close"],
            volume=prices_df["volume"]
        )

        # Company information

        response = requests.get(
            url + "profile",
            params=params,
            timeout=30
        )

        if response.status_code == 402:
            print(f"Company information for {ticker} requires a paid FMP subscription")
            info = {}

        else:
            response.raise_for_status()

            info = response.json()

            if not info:
                print(f"There is not available information for ticker {ticker}")
                info = {}
            else:
                info = info[0]

        # Income statements

        income_history = IncomeStatementHistory()

        response = requests.get(
            url + "income-statement",
            params={**params, "period": "annual", "limit": 20},
            timeout=30
        )

        if response.status_code == 402:
            print(f"Income statement for {ticker} requires a paid FMP subscription")

        else:
            response.raise_for_status()

            income_df = pd.DataFrame(response.json())

            if income_df.empty:
                print(f"There is not available income statement for {ticker}")
            else:
                income_df["date"] = pd.to_datetime(income_df["date"])

                income_df = income_df.set_index("date")

                income_df = income_df.reindex(columns=income)

                for statement_date, row in income_df.iterrows():
                    values = row.tolist()

                    income_history.add(
                        IncomeStatement(statement_date.date(), *values)
                    )

        # Balance sheets

        balance_history = BalanceSheetHistory()

        response = requests.get(
            url + "balance-sheet-statement",
            params={**params, "period": "annual", "limit": 20},
            timeout=30
        )

        if response.status_code == 402:
            print(f"Balance sheet for {ticker} requires a paid FMP subscription")

        else:
            response.raise_for_status()

            balance_df = pd.DataFrame(response.json())

            if balance_df.empty:
                print(f"There is not available balance sheet for {ticker}")
            else:
                balance_df["date"] = pd.to_datetime(balance_df["date"])

                balance_df = balance_df.set_index("date")

                balance_df = balance_df.reindex(columns=balance)

                for statement_date, row in balance_df.iterrows():
                    values = row.tolist()

                    balance_history.add(
                        BalanceSheet(statement_date.date(), *values)
                    )

        # Cash flows

        cashflow_history = CashFlowHistory()

        response = requests.get(
            url + "cash-flow-statement",
            params={**params, "period": "annual", "limit": 20},
            timeout=30
        )

        if response.status_code == 402:
            print(f"Cash flow for {ticker} requires a paid FMP subscription")

        else:
            response.raise_for_status()

            cashflow_df = pd.DataFrame(response.json())

            if cashflow_df.empty:
                print(f"There is not available cash flow for {ticker}")
            else:
                cashflow_df["date"] = pd.to_datetime(cashflow_df["date"])

                cashflow_df = cashflow_df.set_index("date")

                cashflow_df = cashflow_df.reindex(columns=cashflow)

                for statement_date, row in cashflow_df.iterrows():
                    values = row.tolist()

                    cashflow_history.add(
                        CashFlow(statement_date.date(), *values)
                    )

        # Fundamentals

        fundamentals = Fundamentals(
            income_statements=income_history,
            balance_sheets=balance_history,
            cash_flows=cashflow_history
        )

        # Company

        company = Company(
            name=info.get("companyName") or symbol,
            country=info.get("country") or "",
            industry=info.get("industry") or "",
            fundamentals=fundamentals
        )

        # Stock

        return Stock(
            ticker=symbol,
            price=prices,
            company=company
        )

    def get_index(self,symbol: str,period: str = "5y") -> Index:

        base_url = "https://financialmodelingprep.com/stable/"

        today = date.today()

        if period == "max":
            start = date(1900, 1, 1)
        else:
            if not period.endswith("y"):
                raise ValueError("Use periods such as 1y, 5y, 10y or max")

            years = int(period[:-1])
            start = today - timedelta(days=365 * years + 5)

        params = {
            "symbol": symbol,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "apikey": self.api_key
        }

        response = requests.get(
            base_url + "historical-price-eod/full",
            params=params,
            timeout=30
        )

        if response.status_code == 402:
            raise ValueError(
                f"Historical prices for {symbol} require a paid FMP subscription"
            )

        response.raise_for_status()

        prices_df = pd.DataFrame(response.json())

        if prices_df.empty:
            raise ValueError(f"No historical data found for {symbol}")

        prices_df["date"] = pd.to_datetime(prices_df["date"])

        prices_df = prices_df.sort_values("date").set_index("date")

        volume = (
            prices_df["volume"]
            if "volume" in prices_df.columns
            and prices_df["volume"].notna().any()
            and (prices_df["volume"] != 0).any()
            else None
        )

        prices = PriceSeries(
            date=prices_df.index,
            open=prices_df["open"],
            high=prices_df["high"],
            low=prices_df["low"],
            close=prices_df["close"],
            volume=volume
        )

        index_names = {
            "^GSPC": "S&P 500",
            "^NDX": "NASDAQ-100",
            "^DJI": "Dow Jones Industrial Average"
        }

        return Index(
            name=index_names.get(symbol, symbol),
            symbol=symbol,
            country="United States",
            currency="USD",
            exchange=None,
            price=prices,
            constituents=None,
            sector_weights=None
        )