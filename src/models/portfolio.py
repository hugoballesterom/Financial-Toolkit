"""Cartera en USD con posiciones largas/cortas y efectivo firmado.

Modelo sin comisiones, intereses, conversion de divisas ni llamadas de margen.
El efectivo negativo representa financiacion pendiente de incorporar intereses.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date as Date, datetime

import numpy as np
import pandas as pd

from cryptocurrency import Cryptocurrency
from cash_movement import CashMovement
from position import Position
from transaction import ALLOWED_TYPES, Transaction


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
        raise ValueError("Asset requires a price series; bond yields are not prices")
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
        """Saldo firmado tras la ultima operacion; sin intereses."""
        return self._cash

    @property
    def debt(self):
        return max(-self.cash, 0.0)

    @property
    def quantities(self):
        """Vista compatible con el codigo anterior; Position guarda las unidades."""
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
        _close(asset)  # Reject yield-only bonds and assets without usable prices.
        price = _price(asset, date) if price is None else price
        transaction = Transaction(asset, transaction_type, quantity, price, date)
        self._execute([transaction])
        return transaction

    def buy(self, asset, quantity, date, price=None):
        return self._record(asset, "BUY", quantity, date, price)

    def sell(self, asset, quantity, date, price=None):
        return self._record(asset, "SELL", quantity, date, price)

    def deposit(self, amount, date):
        """Aporta efectivo; un saldo negativo se amortiza automaticamente."""
        date = self._check_date(date)
        movement = CashMovement("DEPOSIT", amount, date)
        cash = self.cash + movement.cash_flow
        if not np.isfinite(cash):
            raise ValueError("Deposit exceeds numeric limits")
        # Se necesita valorar la cartera en la fecha del flujo para medir TWR.
        self._equity_at(date)
        self._cash = cash
        self.cash_movements.append(movement)
        return movement

    def withdraw(self, amount, date):
        """Retira efectivo disponible sin financiar la retirada ni patrimonio negativo."""
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

    def _closes(self):
        series = {key: _close(asset) for key, asset in self.assets.items()}
        end = max([self.date] + [s.index[-1] for s in series.values()]
                  + [t.date for t in self.transactions]
                  + [m.date for m in self.cash_movements])
        calendar = pd.date_range(self.date, end, freq="D")
        result = pd.DataFrame(index=calendar)
        for key, close in series.items():
            expanded = close.reindex(close.index.union(calendar)).sort_index()
            if not isinstance(self.assets[key], Cryptocurrency):
                expanded = expanded.ffill()
            result[key] = expanded.reindex(calendar)
        result.index.name = "date"
        return result

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
        """Flujos externos por dia; las compras y ventas no son flujos externos."""
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
        """Retornos ajustados por flujos externos al cierre de cada fecha.

        observed=True calcula entre valoraciones disponibles (no necesariamente diarias).
        Los flujos externos exigen valoracion en su fecha para evitar rentabilidades falsas.
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
        """Retornos entre fechas comunes observables; conserva sus fechas reales."""
        closes = self._closes().dropna(how="any")
        returns = closes.pct_change(fill_method=None).iloc[1:]
        if len(returns) < 2:
            raise ValueError("At least three common price observations are required")
        return returns

    def sampling_info(self):
        """Frecuencia de las fechas comunes usadas por las metricas de activos."""
        self.asset_returns()
        dates = self._closes().dropna(how="any").index
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
        """Estimacion anual aritmetica a pesos actuales, sin costes de financiacion.

        Por defecto anualiza con el intervalo medio observado; aproximacion si es irregular.
        periods permite indicar explicitamente observaciones por ano.
        """
        periods = self.sampling_info()["periods_per_year"] if periods is None else self._periods(periods)
        date = self._closes().dropna(how="any").index[-1]
        last_event = max([self.date] + [t.date for t in self.transactions] + [m.date for m in self.cash_movements])
        if last_event > date:
            raise ValueError("Current risk metrics need a common valuation after the last movement")
        return float(self.weights(date) @ self.asset_returns().mean() * periods)

    def volatility(self, periods=None):
        periods = self.sampling_info()["periods_per_year"] if periods is None else self._periods(periods)
        date = self._closes().dropna(how="any").index[-1]
        # Los pesos historicos solo son validos si no hubo operaciones posteriores.
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
        """Indice TWR en fechas observadas; aportaciones y retiradas no son beneficios."""
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
        """Drawdown observado, ajustado por flujos; puede omitir caidas entre fechas."""
        growth = self.growth()
        return growth / growth.cummax().clip(lower=1) - 1
