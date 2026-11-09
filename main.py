"""End-to-end demo of the toolkit.

Downloads stocks, a cryptocurrency and a benchmark index from Yahoo Finance
(no API key needed), cleans them, builds a portfolio from weights, simulates
it with Monte Carlo and writes the Markdown report and the plots to examples/.

A macro series is added as context: the 3-month Treasury bill rate from FRED
(used as risk-free rate) if FRED_API_KEY is set, or US inflation from the
World Bank otherwise.

Run from the project root:
    python main.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
from dotenv import load_dotenv

from financial_toolkit import AssetFetcher, MacroFetcher, Portfolio

START = "2023-01-03"
END = "2025-10-31"
CAPITAL = 10_000
WEIGHTS = {"AAPL": 0.3, "MSFT": 0.3, "SAN": 0.2, "BTC-USD": 0.2}
BENCHMARK = "^GSPC"
OUTPUT = Path(__file__).parent / "examples"


def main():
    load_dotenv(Path(__file__).parent / ".env")

    # 1. Download and clean the assets (stocks, crypto and benchmark index).
    requests = [
        {"type": "stock", "api": "yfinance", "symbol": "AAPL"},
        {"type": "stock", "api": "yfinance", "symbol": "MSFT"},
        {"type": "stock", "api": "yfinance", "symbol": "SAN"},
        {"type": "crypto", "api": "yfinance", "symbol": "BTC-USD"},
        {"type": "index", "api": "yfinance", "symbol": BENCHMARK},
    ]
    fetcher = AssetFetcher()
    *assets, benchmark = fetcher.get_many(requests, start=START, end=END)
    for symbol, report in fetcher.cleaning_reports.items():
        print(f"{symbol}: {report.n_output} rows, {report.n_dropped} dropped, "
              f"{report.outliers} outliers kept")

    # 2. Macro context and risk-free rate.
    macro = MacroFetcher()
    try:
        bill = macro.get_macro_series("DTB3", source="FRED", start=START, end=END)
        risk_free = float(bill.data.dropna().iloc[-1]) / 100
        print(f"\n{bill.name}: {risk_free:.2%} (risk-free rate)")
    except ValueError:
        inflation = macro.get_macro_series(
            "FP.CPI.TOTL.ZG", source="WB", start=START, end=END, country="US"
        )
        risk_free = 0
        print(f"\nNo FRED_API_KEY: {inflation.name}, mean {inflation.mean:.2f}%")

    # 3. Portfolio, Monte Carlo and report.
    portfolio = Portfolio.from_weights(assets, WEIGHTS, CAPITAL, START)
    simulation = portfolio.monte_carlo(10_000, years=1, seed=42)

    OUTPUT.mkdir(exist_ok=True)
    report = portfolio.report(
        risk_free=risk_free,
        monte_carlo=simulation,
        path=OUTPUT / "portfolio_report.md",
    )
    print("\n" + report)

    simulation.plot()[0].figure.savefig(OUTPUT / "monte_carlo.png", dpi=100)
    portfolio.plots_report(benchmark=benchmark)[0, 0].figure.savefig(
        OUTPUT / "plots_report.png", dpi=100
    )
    print(f"Report and plots saved in {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
