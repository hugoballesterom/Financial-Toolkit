"""USD portfolio with long/short positions and signed cash.

Model without fees, interest, currency conversion or margin calls.
Negative cash is financing whose interest is not modelled yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date as Date
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from .cash_movement import CashMovement
from .cleaning import OUTLIER_STD, find_outliers
from .cryptocurrency import Cryptocurrency
from .monte_carlo import MonteCarloResult
from .position import Position
from .transaction import ALLOWED_TYPES, Transaction


def _date(value):
    if not isinstance(value, (str, Date, datetime, pd.Timestamp)):
        raise ValueError("Expected a date")
    value = pd.Timestamp(value)
    if pd.isna(value):
        raise ValueError("Invalid date")
    return value.tz_localize(None).normalize()


def _asset_id(asset):
    return getattr(asset, "ticker", None) or asset.symbol


def _close(asset):
    if not isinstance(asset, ALLOWED_TYPES):
        raise TypeError("Invalid asset type")
    if getattr(asset, "price", None) is None:
        raise ValueError("Asset requires a price series")
    close = asset.price.close.copy()
    if close.empty:
        raise ValueError("Empty price series")
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    if close.index.hasnans or close.index.has_duplicates:
        raise ValueError("Price timestamps must be valid and unique")
    close = pd.to_numeric(close, errors="raise")
    if ((close <= 0) | np.isinf(close)).any():
        raise ValueError("Observed prices must be positive and finite")
    close = close.sort_index().resample("D").last().dropna()
    if close.empty:
        raise ValueError("No valid prices")
    return close


def _price(asset, date):
    date = _date(date)
    closes = _close(asset)
    if isinstance(asset, Cryptocurrency):
        if date not in closes.index:
            raise ValueError(f"No observed crypto price on {date.date()}")
        return float(closes.loc[date])
    known = closes.loc[:date]
    if known.empty:
        raise ValueError(f"No price on or before {date.date()}")
    return float(known.iloc[-1])


def _check_weights(assets, weights):
    assets = list(assets)
    ids = [_asset_id(asset) for asset in assets]
    if not assets or len(set(ids)) != len(ids):
        raise ValueError("Provide assets with unique identifiers")
    if isinstance(weights, Mapping):
        if set(weights) != set(ids):
            raise ValueError("Provide exactly one weight for each asset")
        weights = [weights[key] for key in ids]
    raw = list(weights)
    if len(raw) != len(assets) or any(isinstance(w, (bool, np.bool_)) for w in raw):
        raise ValueError("Provide one numeric weight per asset")
    values = np.asarray(raw, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Weights must be finite numbers")
    # No sum constraint: the residual is cash, possibly negative.
    return assets, dict(zip(ids, values))


def _markdown_table(frame):
    """Markdown table of a DataFrame whose values are already formatted."""
    header = "| " + " | ".join([frame.index.name or ""] + list(frame.columns)) + " |"
    separator = "|" + "---|" * (len(frame.columns) + 1)
    rows = [
        "| " + " | ".join([str(index)] + [str(value) for value in row]) + " |"
        for index, row in zip(frame.index, frame.to_numpy())
    ]
    return "\n".join([header, separator, *rows])


REPORT_SECTIONS = ("summary", "assets", "monte_carlo", "warnings")


@dataclass
class Portfolio:
    capital: float
    date: pd.Timestamp
    currency: str = "USD"
    assets: dict = field(default_factory=dict, init=False)
    positions: dict = field(default_factory=dict, init=False)
    transactions: list = field(default_factory=list, init=False)
    cash_movements: list = field(default_factory=list, init=False)
    target_weights: dict = field(default_factory=dict, init=False)
    _cash: float = field(init=False, repr=False)

    def __post_init__(self):
        if isinstance(self.capital, bool):
            raise ValueError("Capital must be positive and finite")
        self.capital = float(self.capital)
        if not np.isfinite(self.capital) or self.capital <= 0:
            raise ValueError("Capital must be positive and finite")
        self.date = _date(self.date)
        if self.currency != "USD":
            raise ValueError("Only USD is supported until FX conversion is implemented")
        self._cash = self.capital

    @property
    def cash(self):
        """Signed balance after the last operation; no interest."""
        return self._cash

    @property
    def debt(self):
        return max(-self.cash, 0.0)

    @property
    def quantities(self):
        """View kept for older code; Position stores the units."""
        return {key: position.quantity for key, position in self.positions.items()}

    @classmethod
    def from_weights(cls, assets, weights, capital, date):
        portfolio = cls(capital=capital, date=date)
        portfolio.rebalance(assets, weights, date)
        return portfolio

    def _check_date(self, date):
        date = _date(date)
        last = self.transactions[-1].date if self.transactions else self.date
        if self.cash_movements:
            last = max(last, self.cash_movements[-1].date)
        if date < last:
            raise ValueError("Operations must be chronological and not precede inception")
        return date

    def _execute(self, transactions):
        # Prepare copies first: a failed batch must not leave partial trades.
        positions = {key: replace(value) for key, value in self.positions.items()}
        assets = self.assets.copy()
        cash = self.cash
        for transaction in transactions:
            asset = transaction.asset
            key = _asset_id(asset)
            known_currency = getattr(asset, "currency", None)
            if known_currency and str(known_currency).upper() != self.currency:
                raise ValueError("Convert asset prices to USD before trading")
            if key in assets and assets[key] is not asset:
                raise ValueError("Reuse the same asset object for an existing identifier")
            position = positions.setdefault(key, Position(asset))
            position.apply_transaction(transaction)
            cash += transaction.cash_flow
            if not np.isfinite(cash) or not np.isfinite(position.quantity):
                raise ValueError("Operation exceeds numeric limits")
            assets[key] = asset
        self.positions = positions
        self.assets = assets
        self._cash = cash
        self.transactions.extend(transactions)

    def _record(self, asset, transaction_type, quantity, date, price=None):
        date = self._check_date(date)
        _close(asset)  # Reject assets without usable prices.
        price = _price(asset, date) if price is None else price
        transaction = Transaction(asset, transaction_type, quantity, price, date)
        self._execute([transaction])
        return transaction

    def buy(self, asset, quantity, date, price=None):
        return self._record(asset, "BUY", quantity, date, price)

    def sell(self, asset, quantity, date, price=None):
        return self._record(asset, "SELL", quantity, date, price)

    def deposit(self, amount, date):
        """Add cash; a negative balance is paid down automatically."""
        date = self._check_date(date)
        movement = CashMovement("DEPOSIT", amount, date)
        cash = self.cash + movement.cash_flow
        if not np.isfinite(cash):
            raise ValueError("Deposit exceeds numeric limits")
        # The portfolio must be valued on the flow date to measure TWR.
        self._equity_at(date)
        self._cash = cash
        self.cash_movements.append(movement)
        return movement

    def withdraw(self, amount, date):
        """Withdraw available cash, without financing it or leaving negative equity."""
        date = self._check_date(date)
        movement = CashMovement("WITHDRAW", amount, date)
        if movement.amount > self.cash:
            raise ValueError("Withdrawal exceeds available cash; sell assets or deposit first")
        equity = self._equity_at(date)
        if movement.amount > equity:
            raise ValueError("Withdrawal would leave negative equity")
        self._cash += movement.cash_flow
        self.cash_movements.append(movement)
        return movement

    def _equity_at(self, date):
        equity = self.cash + sum(
            position.quantity * _price(position.asset, date)
            for position in self.positions.values() if position.quantity != 0
        )
        if not np.isfinite(equity):
            raise ValueError("Equity is not finite")
        return equity

    def rebalance(self, assets, weights, date):
        date = self._check_date(date)
        assets, targets = _check_weights(assets, weights)
        universe = self.assets.copy()
        for asset in assets:
            key = _asset_id(asset)
            if key in universe and universe[key] is not asset:
                raise ValueError("Reuse the same asset object for an existing identifier")
            universe[key] = asset
        # Price all assets involved before recording any operation.
        prices = {
            key: _price(asset, date)
            for key, asset in universe.items()
            if self.quantities.get(key, 0) != 0 or targets.get(key, 0) != 0
        }
        equity = self.cash + sum(
            quantity * prices[key]
            for key, quantity in self.quantities.items() if quantity != 0
        )
        if not np.isfinite(equity) or equity <= 0:
            raise ValueError("Rebalancing requires positive equity")
        operations = []
        for key, asset in universe.items():
            weight = targets.get(key, 0.0)
            previous = self.quantities.get(key, 0.0)
            if weight == 0 and previous == 0:
                continue
            change = weight * equity / prices[key] - previous
            if change == 0:
                continue
            operations.append(Transaction(
                asset, "BUY" if change > 0 else "SELL",
                abs(change), prices[key], date,
            ))
        self._execute(operations)
        self.target_weights = targets

    def _start(self):
        return self.date

    def _closes(self, observed=False):
        """Closes on a daily calendar.

        By default stocks and indices carry their last close forward, which
        is right for valuation. With observed=True every asset only has a
        price on the days it was actually observed.
        """
        series = {key: _close(asset) for key, asset in self.assets.items()}
        end = max([self.date] + [s.index[-1] for s in series.values()]
                  + [t.date for t in self.transactions]
                  + [m.date for m in self.cash_movements])
        calendar = pd.date_range(self.date, end, freq="D")
        result = pd.DataFrame(index=calendar)
        for key, close in series.items():
            expanded = close.reindex(close.index.union(calendar)).sort_index()
            if not observed and not isinstance(self.assets[key], Cryptocurrency):
                expanded = expanded.ffill()
            result[key] = expanded.reindex(calendar)
        result.index.name = "date"
        return result

    def _common_closes(self):
        """Closes on the days every asset has an observed price, without filling.

        Risk metrics use these dates: filled weekends would add false zero
        returns and count calendar days as observations.
        """
        return self._closes(observed=True).dropna(how="any")

    def _positions(self):
        closes = self._closes()
        quantities = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for transaction in self.transactions:
            quantities.loc[transaction.date:, _asset_id(transaction.asset)] += (
                transaction.signed_quantity
            )
        return quantities

    def cash_history(self):
        cash = pd.Series(self.capital, index=self._closes().index, name="cash")
        for transaction in self.transactions:
            cash.loc[transaction.date:] += transaction.cash_flow
        for movement in self.cash_movements:
            cash.loc[movement.date:] += movement.cash_flow
        return cash

    def external_cash_flows(self):
        """External flows per day; buys and sells are not external flows."""
        flows = pd.Series(0.0, index=self._closes().index, name="external_cash_flow")
        for movement in self.cash_movements:
            flows.loc[movement.date] += movement.cash_flow
        return flows

    def _position_values(self):
        quantities = self._positions()
        # No price is needed when the position is zero.
        return (quantities * self._closes()).mask(quantities == 0, 0.0)

    def value(self):
        values = self._position_values()
        holdings = values.sum(axis=1).mask(values.isna().any(axis=1))
        return (holdings + self.cash_history()).rename("equity")

    def weights(self, date=None):
        values = self._position_values()
        date = values.index[-1] if date is None else _date(date)
        if date not in values.index:
            raise ValueError("Date is outside the portfolio history")
        row = values.loc[date]
        equity = self.value().loc[date]
        if row.isna().any() or not np.isfinite(equity) or equity <= 0:
            raise ValueError("Weights require complete prices and positive equity")
        return row / equity

    def cash_weight(self, date=None):
        weights = self.weights(date)
        return 1.0 - weights.sum()

    def gross_exposure(self, date=None):
        return self.weights(date).abs().sum()

    def net_exposure(self, date=None):
        return self.weights(date).sum()

    def update_prices(self, date=None):
        closes = self._closes()
        date = closes.index[-1] if date is None else _date(date)
        if self.transactions and date < self.transactions[-1].date:
            raise ValueError("Cannot mark current positions before the last trade")
        if date not in closes.index:
            raise ValueError("Date is outside the portfolio history")
        updates = {}
        for key, position in self.positions.items():
            if position.quantity != 0:
                price = closes.loc[date, key]
                if pd.isna(price):
                    raise ValueError(f"Missing price for {key} on {date.date()}")
                updates[key] = price
        for key, price in updates.items():
            self.positions[key].update_price(price)

    def returns(self, observed=False):
        """Returns adjusted for external flows at each date's close.

        observed=True computes them between available valuations (not
        necessarily daily). External flows need a valuation on their date to
        avoid false returns.
        """
        equity = self.value()
        flows = self.external_cash_flows()
        if observed:
            equity = equity.dropna()
            missing_flow_dates = flows[(flows != 0) & ~flows.index.isin(equity.index)]
            if not missing_flow_dates.empty:
                raise ValueError("External cash flows require an observed equity valuation")
        flows = flows.reindex(equity.index, fill_value=0)
        result = (equity - flows) / equity.shift(1) - 1
        return result.where(equity.shift(1) > 0).rename("return")

    def log_returns(self):
        returns = self.returns()
        if (returns.dropna() <= -1).any():
            raise ValueError("Log returns are undefined for losses of 100% or more")
        return np.log1p(returns)

    def asset_returns(self):
        """Returns between observed common dates; keeps their real dates."""
        closes = self._common_closes()
        returns = closes.pct_change(fill_method=None).iloc[1:]
        if len(returns) < 2:
            raise ValueError("At least three common price observations are required")
        return returns

    def sampling_info(self):
        """Frequency of the common dates used by the asset metrics."""
        self.asset_returns()
        dates = self._common_closes().index
        intervals = np.diff(dates.values) / np.timedelta64(1, "D")
        mean_days = float(intervals.mean())
        return {
            "price_observations": len(dates),
            "return_observations": len(intervals),
            "mean_days": mean_days,
            "regular": bool(np.allclose(intervals, intervals[0])),
            "periods_per_year": 365 / mean_days,
        }

    @staticmethod
    def _periods(periods):
        if isinstance(periods, bool) or not np.isfinite(periods) or periods <= 0:
            raise ValueError("periods must be positive and finite")
        return periods

    def expected_return(self, periods=None):
        """Annual arithmetic estimate at current weights, without financing costs.

        By default it annualizes with the mean observed interval, an
        approximation if sampling is irregular. periods sets the number of
        observations per year explicitly.
        """
        periods = self.sampling_info()["periods_per_year"] if periods is None else self._periods(periods)
        date = self._common_closes().index[-1]
        last_event = max([self.date] + [t.date for t in self.transactions] + [m.date for m in self.cash_movements])
        if last_event > date:
            raise ValueError("Current risk metrics need a common valuation after the last movement")
        return float(self.weights(date) @ self.asset_returns().mean() * periods)

    def volatility(self, periods=None):
        periods = self.sampling_info()["periods_per_year"] if periods is None else self._periods(periods)
        date = self._common_closes().index[-1]
        # Historical weights are only valid if there were no later operations.
        last_event = max([self.date] + [t.date for t in self.transactions] + [m.date for m in self.cash_movements])
        if last_event > date:
            raise ValueError("Current risk metrics need a common valuation after the last movement")
        weights = self.weights(date)
        covariance = self.asset_returns().cov()
        variance = float(weights @ covariance @ weights)
        return float(np.sqrt(max(variance, 0.0) * self._periods(periods)))

    def sharpe(self, risk_free=0, periods=None):
        if not np.isfinite(risk_free):
            raise ValueError("risk_free must be finite")
        volatility = self.volatility(periods)
        if volatility == 0:
            raise ValueError("Sharpe is undefined when volatility is zero")
        return (self.expected_return(periods) - risk_free) / volatility

    def correlations(self):
        return self.asset_returns().corr()

    def growth(self):
        """TWR index on observed dates; deposits and withdrawals are not gains."""
        equity = self.value().dropna()
        if equity.empty or equity.index[0] != self.date:
            raise ValueError("Growth requires an initial equity valuation")
        returns = self.returns(observed=True)
        if returns.iloc[1:].isna().any():
            raise ValueError("Growth cannot continue after zero or negative equity")
        initial_base = self.capital + self.external_cash_flows().iloc[0]
        if initial_base <= 0:
            raise ValueError("Growth requires positive initial equity")
        factors = 1 + returns
        factors.iloc[0] = equity.iloc[0] / initial_base
        return factors.cumprod().rename("growth")

    def drawdown(self):
        """Observed drawdown, adjusted for flows; it can miss falls between dates."""
        growth = self.growth()
        return growth / growth.cummax().clip(lower=1) - 1

    def monte_carlo(
        self,
        n_simulations: int = 10_000,
        years: float = 1.0,
        *,
        asset: str | None = None,
        seed: int | None = None,
    ) -> MonteCarloResult:
        """Simulate future values with normal log returns per step.

        The portfolio is simulated with its current weights held fixed (cash
        earns 0). With asset, only that asset is simulated from its last price.

        Args:
            n_simulations: Number of simulated paths.
            years: Horizon. Converted to steps with periods_per_year.
            asset: Identifier of one asset, or None for the whole portfolio.
            seed: Seed for reproducible results.

        Returns:
            Simulated paths and the parameters used to generate them.

        Raises:
            ValueError: If n_simulations or years are not positive, the asset
                is unknown, the portfolio has no assets, there is a movement
                after the last common price date, a historical return is
                -100% or worse, or the horizon is shorter than one step.
        """
        # 1. Validate the arguments and the reference date.
        if (
            isinstance(n_simulations, bool)
            or not isinstance(n_simulations, (int, np.integer))
            or n_simulations <= 0
        ):
            raise ValueError(
                f"n_simulations must be a positive integer, got {n_simulations!r}"
            )
        if (
            isinstance(years, bool)
            or not isinstance(years, (int, float, np.number))
            or not np.isfinite(years)
            or years <= 0
        ):
            raise ValueError(f"years must be positive and finite, got {years!r}")
        if not self.assets:
            raise ValueError("Portfolio has no assets to simulate")
        if asset is not None and asset not in self.assets:
            raise ValueError(
                f"asset must be one of {sorted(self.assets)}, got {asset!r}"
            )
        common = self._common_closes()
        if common.empty:
            raise ValueError("Simulation requires a date with prices for every asset")
        date = common.index[-1]
        last_event = max(
            [self.date]
            + [t.date for t in self.transactions]
            + [m.date for m in self.cash_movements]
        )
        if last_event > date:
            raise ValueError(
                "Simulation needs a common valuation after the last movement"
            )

        # 2. Historical simple returns of the portfolio or of the asset.
        asset_returns = self.asset_returns()
        if asset is None:
            returns = asset_returns @ self.weights(date)
        else:
            returns = asset_returns[asset]

        # 3. Log returns per step.
        if (returns <= -1).any():
            raise ValueError("Log returns are undefined for losses of 100% or more")
        log_returns = np.log1p(returns)
        mu = float(log_returns.mean())
        sigma = float(log_returns.std())

        # 4. Initial value.
        if asset is None:
            initial_value = float(self.value().loc[date])
        else:
            initial_value = float(common.loc[date, asset])

        # 5. Random log returns, one row per step and one column per path.
        periods_per_year = self.sampling_info()["periods_per_year"]
        steps = round(years * periods_per_year)
        if steps < 1:
            raise ValueError(
                f"years must cover at least one step, got {years!r} "
                f"with {periods_per_year:.1f} steps per year"
            )
        rng = np.random.default_rng(seed)
        draws = rng.normal(mu, sigma, size=(steps, n_simulations))

        # 6. Value paths, with row 0 equal to the initial value.
        cumulative = np.vstack([np.zeros((1, n_simulations)), draws.cumsum(axis=0)])
        paths = pd.DataFrame(initial_value * np.exp(cumulative))
        paths.index.name = "step"
        paths.columns.name = "simulation"

        # 7. Result.
        return MonteCarloResult(
            paths=paths,
            target=asset or "portfolio",
            mu=mu,
            sigma=sigma,
            periods_per_year=periods_per_year,
            seed=seed,
        )

    def report(
        self,
        sections=REPORT_SECTIONS,
        *,
        risk_free=0,
        periods=None,
        monte_carlo=None,
        max_weight=0.4,
        max_correlation=0.8,
        max_drawdown=-0.2,
        min_observations=60,
        path=None,
    ):
        """Markdown report with key metrics, diagnostics and risk warnings.

        Args:
            sections: Sections to include, in order, from REPORT_SECTIONS.
            risk_free: Annual risk-free rate for the Sharpe ratio.
            periods: Observations per year; None uses the observed frequency.
            monte_carlo: Result of monte_carlo() to summarize, or None.
            max_weight: Absolute weight above which an asset is a
                concentration warning.
            max_correlation: Correlation above which a pair of assets is a
                diversification warning.
            max_drawdown: Drawdown below which the portfolio gets a warning.
            min_observations: Common return observations below which the
                metrics get a warning.
            path: File where the report is also saved, or None.

        Returns:
            The report as Markdown text.

        Raises:
            ValueError: If a section is unknown or monte_carlo is requested
                without a result.
        """
        unknown = set(sections) - set(REPORT_SECTIONS)
        if unknown:
            raise ValueError(
                f"sections must be in {REPORT_SECTIONS}, got {sorted(unknown)}"
            )
        if monte_carlo is not None and not isinstance(monte_carlo, MonteCarloResult):
            raise ValueError(
                f"monte_carlo must be a MonteCarloResult, got {type(monte_carlo).__name__}"
            )

        warnings = []

        def metric(function, text):
            # A metric that cannot be computed is reported, not raised.
            try:
                return text.format(function())
            except ValueError as error:
                warnings.append(f"Metric not available: {error}.")
                return "n/a"

        common = self._common_closes()
        date = common.index[-1] if not common.empty else self.date
        lines = [
            "# Portfolio report",
            "",
            f"From {self.date.date()} to {date.date()} · {self.currency} · "
            f"{len(self.assets)} assets",
        ]

        for section in sections:
            # 1. Portfolio metrics.
            if section == "summary":
                rows = {
                    "Equity": metric(lambda: self.value().loc[date], "{:,.2f}"),
                    "Initial capital": f"{self.capital:,.2f}",
                    "Total return (TWR)": metric(lambda: self.growth().iloc[-1] - 1, "{:.2%}"),
                    "Annual expected return": metric(
                        lambda: self.expected_return(periods), "{:.2%}"),
                    "Annual volatility": metric(lambda: self.volatility(periods), "{:.2%}"),
                    "Sharpe ratio": metric(lambda: self.sharpe(risk_free, periods), "{:.2f}"),
                    "Max drawdown": metric(lambda: self.drawdown().min(), "{:.2%}"),
                    "Cash": f"{self.cash:,.2f}",
                    "Cash weight": metric(lambda: self.cash_weight(date), "{:.2%}"),
                    "Gross exposure": metric(lambda: self.gross_exposure(date), "{:.2%}"),
                    "Net exposure": metric(lambda: self.net_exposure(date), "{:.2%}"),
                    "Return observations": metric(
                        lambda: self.sampling_info()["return_observations"], "{:,}"),
                }
                table = pd.DataFrame({"Value": rows})
                table.index.name = "Metric"
                lines += ["", "## Summary", "", _markdown_table(table)]

            # 2. Metrics per asset, from the statistics of each PriceSeries.
            elif section == "assets":
                try:
                    weights = self.weights(date)
                except ValueError:
                    weights = pd.Series(np.nan, index=list(self.assets))
                table = pd.DataFrame({
                    key: {
                        "Type": type(asset).__name__,
                        "Weight": f"{weights.get(key, np.nan):.2%}",
                        "Last price": f"{asset.price.current_price():,.2f}",
                        "Annual log return": f"{asset.price.annual_return:.2%}",
                        "Annual volatility": f"{asset.price.annual_volatility:.2%}",
                        "Max drawdown": f"{asset.price.max_drawdown():.2%}",
                    }
                    for key, asset in self.assets.items()
                }).T
                table.index.name = "Asset"
                lines += ["", "## Assets", "", _markdown_table(table)]

            # 3. Monte Carlo summary.
            elif section == "monte_carlo":
                if monte_carlo is None:
                    continue
                summary = monte_carlo.summary()
                years = (monte_carlo.paths.shape[0] - 1) / monte_carlo.periods_per_year
                rows = {
                    "Simulations": f"{monte_carlo.paths.shape[1]:,}",
                    "Horizon (years)": f"{years:.2f}",
                    "Mean return": f"{summary['mean']:.2%}",
                    "Median return": f"{summary['median']:.2%}",
                    "VaR 95%": f"{summary['var_95']:.2%}",
                    "CVaR 95%": f"{summary['cvar_95']:.2%}",
                    "VaR 99%": f"{summary['var_99']:.2%}",
                    "CVaR 99%": f"{summary['cvar_99']:.2%}",
                    "Loss probability": f"{summary['loss_probability']:.2%}",
                }
                table = pd.DataFrame({"Value": rows})
                table.index.name = f"Monte Carlo: {monte_carlo.target}"
                lines += ["", "## Monte Carlo", "", _markdown_table(table)]

            # 4. Diagnostics and risk warnings.
            elif section == "warnings":
                try:
                    weights = self.weights(date)
                    for key, weight in weights[weights.abs() > max_weight].items():
                        warnings.append(
                            f"Concentration: {key} weighs {weight:.1%} "
                            f"(limit {max_weight:.0%})."
                        )
                    for key, weight in weights[weights < 0].items():
                        warnings.append(
                            f"Short position in {key} ({weight:.1%}): losses are unlimited."
                        )
                except ValueError:
                    pass
                if self.cash < 0:
                    warnings.append(
                        f"Negative cash ({self.cash:,.2f}): the portfolio is leveraged "
                        "and financing costs are not modelled."
                    )
                try:
                    correlations = self.correlations()
                    keys = list(correlations.columns)
                    for i, first in enumerate(keys):
                        for second in keys[i + 1:]:
                            value = correlations.loc[first, second]
                            if value > max_correlation:
                                warnings.append(
                                    f"High correlation between {first} and {second} "
                                    f"({value:.2f}): little diversification."
                                )
                    observations = self.sampling_info()["return_observations"]
                    if observations < min_observations:
                        warnings.append(
                            f"Only {observations} common return observations: "
                            "the metrics are not reliable."
                        )
                except ValueError:
                    pass
                try:
                    worst = self.drawdown().min()
                    if worst < max_drawdown:
                        warnings.append(f"Max drawdown of {worst:.1%} (limit {max_drawdown:.0%}).")
                except ValueError:
                    pass
                for key, asset in self.assets.items():
                    outliers = find_outliers(_close(asset))
                    if len(outliers):
                        warnings.append(
                            f"{key}: {len(outliers)} return(s) beyond {OUTLIER_STD} standard "
                            "deviations, kept: check that they are real and not data errors."
                        )
                if monte_carlo is not None and monte_carlo.loss_probability() > 0.5:
                    warnings.append(
                        f"Monte Carlo loss probability of {monte_carlo.loss_probability():.1%}."
                    )
                lines += ["", "## Risk warnings", ""]
                lines += [f"- {text}" for text in dict.fromkeys(warnings)] or ["- No warnings."]

        text = "\n".join(lines) + "\n"
        if path is not None:
            with open(path, "w", encoding="utf-8") as file:
                file.write(text)
        return text

    def plots_report(self, benchmark=None, figsize=(14, 14)):
        """Charts of the evolution, performance, correlation and risk.

        Panels: equity value, drawdown, cumulative performance of each asset
        and of the portfolio (with an optional benchmark), correlation
        matrix, current weights and annual risk against return per asset.

        Args:
            benchmark: Stock or Index to compare with, or None.
            figsize: Size of the whole figure.

        Returns:
            The matplotlib axes. In a script call plt.show() to see them.
        """
        fig, axes = plt.subplots(3, 2, figsize=figsize)
        common = self._common_closes()
        date = common.index[-1]

        # 1. Equity value.
        ax = axes[0, 0]
        self.value().dropna().plot(ax=ax, color="tab:blue")
        ax.set_title(f"Portfolio value ({self.currency})")
        ax.set_xlabel("")

        # 2. Drawdown.
        ax = axes[0, 1]
        drawdown = self.drawdown()
        ax.fill_between(drawdown.index, drawdown, 0, color="tab:red", alpha=0.4)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title("Drawdown")

        # 3. Cumulative performance on common dates.
        ax = axes[1, 0]
        (common / common.iloc[0]).plot(ax=ax, lw=1, alpha=0.8)
        growth = self.growth()
        (growth / growth.iloc[0]).plot(ax=ax, color="black", lw=2, label="Portfolio")
        if benchmark is not None:
            close = _close(benchmark).loc[self.date:date]
            (close / close.iloc[0]).plot(
                ax=ax, color="grey", ls="--", lw=1.5, label=f"Benchmark {_asset_id(benchmark)}"
            )
        ax.axhline(1, color="grey", lw=0.8)
        ax.set_title("Cumulative performance (start = 1)")
        ax.set_xlabel("")
        ax.legend(fontsize=8)

        # 4. Correlation matrix.
        ax = axes[1, 1]
        correlations = self.correlations()
        image = ax.imshow(correlations, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(correlations)), correlations.columns, rotation=45, ha="right")
        ax.set_yticks(range(len(correlations)), correlations.index)
        for i in range(len(correlations)):
            for j in range(len(correlations)):
                value = correlations.iloc[i, j]
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(value) > 0.6 else "black")
        fig.colorbar(image, ax=ax, shrink=0.8)
        ax.set_title("Correlation of returns")

        # 5. Current weights, cash included.
        ax = axes[2, 0]
        weights = self.weights(date)
        weights["Cash"] = self.cash_weight(date)
        ax.bar(weights.index, weights, color=["tab:blue"] * (len(weights) - 1) + ["tab:grey"])
        ax.axhline(0, color="grey", lw=0.8)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title(f"Weights on {date.date()}")

        # 6. Annual risk against return, same frequency as the metrics.
        ax = axes[2, 1]
        returns = self.asset_returns()
        periods = self.sampling_info()["periods_per_year"]
        ax.scatter(returns.std() * np.sqrt(periods), returns.mean() * periods, color="tab:blue")
        for key in returns.columns:
            ax.annotate(key, (returns[key].std() * np.sqrt(periods), returns[key].mean() * periods),
                        fontsize=8, xytext=(4, 4), textcoords="offset points")
        ax.scatter(self.volatility(), self.expected_return(), color="black", marker="*", s=150,
                   label="Portfolio")
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_xlabel("Annual volatility")
        ax.set_ylabel("Annual expected return")
        ax.set_title("Risk and return")
        ax.legend(fontsize=8)

        fig.tight_layout()
        return axes
