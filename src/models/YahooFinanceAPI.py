from dataclasses import dataclass, fields

from datetime import date
import logging
import math
import pandas as pd
import yfinance as yf

from index import Index
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

income = [
    "Total Revenue",
    "Cost Of Revenue",
    "Gross Profit",
    "Operating Expense",
    "Operating Income",
    "Interest Expense",
    "Pretax Income",
    "Tax Provision",
    "Net Income"
]

balance = [
    "Cash Cash Equivalents And Short Term Investments",
    "Total Debt",
    "Accounts Receivable",
    "Inventory",
    "Current Assets",
    "Net PPE",
    "Goodwill And Other Intangible Assets",
    "Total Assets",
    "Current Liabilities",
    "Long Term Debt",
    "Total Liabilities Net Minority Interest",
    "Stockholders Equity"
]


cashflow = [
    "Net Income From Continuing Operations",
    "Depreciation And Amortization",
    "Change In Working Capital",
    "Operating Cash Flow",
    "Capital Expenditure",
    "Investing Cash Flow",
    "Issuance Of Debt",
    "Repayment Of Debt",
    "Repurchase Of Capital Stock",
    "Cash Dividends Paid",
    "Financing Cash Flow",
    "Changes In Cash"
]


@dataclass
class YahooFinanceAPI:

    def get_stock(self, ticker: str, period: str = '5y', interval: str = '1d') -> Stock:

        assert len(ticker) > 0, "The ticker must not be empty"
        symbol = ticker
        yahoo = yf.Ticker(symbol)
        prices_df = yahoo.history(period=period,interval=interval,auto_adjust=True)
        assert not prices_df.empty, f"The ticker {ticker} has not been found"

        prices = PriceSeries(
                date=prices_df.index,
                open=prices_df["Open"],
                high=prices_df["High"],
                low=prices_df["Low"],
                close=prices_df["Close"],
                volume=prices_df["Volume"]) 
          
        info=yahoo.info
        if not info:
            print(f"There is not available information for ticker {ticker}")
            info={}

        income_history = IncomeStatementHistory()
        income_df=yahoo.income_stmt.reindex(income)
        if income_df.empty:
            print(f"There is not available income statement for {ticker}")
        else:
            for column in income_df.columns:
                values = income_df[column].tolist()
                income_history.add(IncomeStatement(column.date(), *values))

        balance_history = BalanceSheetHistory()
        balance_df=yahoo.balance_sheet.reindex(balance)
        if balance_df.empty:
            print(f"There is not available balance sheet for {ticker}")
        else:
            for column in balance_df.columns:
                values=balance_df[column].tolist()
                balance_history.add(BalanceSheet(column.date(), *values))
        
        cashflow_history = CashFlowHistory()
        cashflow_df=yahoo.cashflow.reindex(cashflow)
        if cashflow_df.empty:
            print(f"There is not cashflow for {ticker} ")
        else:
            for column in cashflow_df:
                values=cashflow_df[column].tolist()
                cashflow_history.add(CashFlow(column.date(), *values))

        fundamentals = Fundamentals(
                       income_statements=income_history,
                       balance_sheets=balance_history,
                       cash_flows=cashflow_history)

        company = Company(
        name=info.get('longName') or info.get('shortName') or symbol,
        country=info.get('country') or '',
        industry=info.get('industry') or '',
        fundamentals=fundamentals)

        return Stock(ticker=symbol,price=prices,company=company)

    def get_index(self,symbol: str,start: str = "2020-01-01",end: str = None, etf_symbol: str = None) -> Index:

        ticker = yf.Ticker(symbol)

        prices_df = ticker.history(
            start=start,
            end=end,
            auto_adjust=False
        )

        if prices_df.empty:
            raise ValueError(f"The index {symbol} has not been found")

        prices_df = prices_df.sort_index()

        volume = (
            prices_df["Volume"]
            if "Volume" in prices_df.columns
            and prices_df["Volume"].notna().any()
            and (prices_df["Volume"] != 0).any()
            else None
        )

        prices = PriceSeries(
            date=prices_df.index,
            open=prices_df["Open"],
            high=prices_df["High"],
            low=prices_df["Low"],
            close=prices_df["Close"],
            volume=volume
        )

        info = ticker.info

        name = info.get("longName") or info.get("shortName") or symbol
        country = info.get("country")
        currency = info.get("currency")
        exchange = info.get("exchange")

        constituents = None
        sector_weights = None

        if etf_symbol is not None:

            etf = yf.Ticker(etf_symbol)

            try:
                holdings = etf.funds_data.top_holdings

                if holdings is not None and not holdings.empty:
                    constituents = holdings.copy()

            except (AttributeError, KeyError, ValueError) as e:
                print(f"Could not retrieve ETF holdings: {e}")

            try:
                sectors = etf.funds_data.sector_weightings

                if sectors:
                    sector_weights = sectors

            except (AttributeError, KeyError, ValueError) as e:
                print(f"Could not retrieve sector weights: {e}")

        index = Index(
            name=name,
            symbol=symbol,
            country=country,
            currency=currency,
            exchange=exchange,
            price=prices,
            constituents=constituents,
            sector_weights=sector_weights
        )

        return index

