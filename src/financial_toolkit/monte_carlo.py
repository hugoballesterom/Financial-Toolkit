from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


def _check_level(level: float) -> float:
    if isinstance(level, bool) or not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, got {level!r}")
    return level


@dataclass(frozen=True)
class MonteCarloResult:
    """Simulated value paths of a portfolio or a single asset.

    All statistics (mean, median, percentiles, VaR, CVaR) refer to the simple
    return of each simulation over the whole horizon.

    Attributes:
        paths: Simulated values. One row per step (row 0 is today) and one
            column per simulation.
        target: 'portfolio' or the identifier of the simulated asset.
        mu: Mean log return per step used to simulate.
        sigma: Standard deviation of the log return per step.
        periods_per_year: Steps in one year, from the data frequency.
        seed: Seed of the random generator, or None.
    """

    paths: pd.DataFrame
    target: str
    mu: float
    sigma: float
    periods_per_year: float
    seed: int | None

    def __post_init__(self):
        if not isinstance(self.paths, pd.DataFrame):
            raise TypeError(
                f"paths must be a DataFrame, got {type(self.paths).__name__}"
            )
        if self.paths.shape[0] < 2 or self.paths.shape[1] < 1:
            raise ValueError(
                "paths must have at least 2 steps and 1 simulation, "
                f"got shape {self.paths.shape}"
            )
        values = self.paths.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("paths must contain positive finite values")
        if not np.isfinite(self.mu):
            raise ValueError(f"mu must be finite, got {self.mu!r}")
        if not np.isfinite(self.sigma) or self.sigma < 0:
            raise ValueError(f"sigma must be non-negative and finite, got {self.sigma!r}")
        if not np.isfinite(self.periods_per_year) or self.periods_per_year <= 0:
            raise ValueError(
                f"periods_per_year must be positive, got {self.periods_per_year!r}"
            )

    @property
    def initial_value(self) -> float:
        """Value today, shared by every simulation."""
        return float(self.paths.iloc[0, 0])

    @property
    def final_returns(self) -> pd.Series:
        """Simple return of each simulation over the whole horizon."""
        return (self.paths.iloc[-1] / self.paths.iloc[0] - 1).rename('final_return')

    def mean(self) -> float:
        """Mean final return across simulations."""
        return float(self.final_returns.mean())

    def median(self) -> float:
        """Median final return across simulations."""
        return float(self.final_returns.median())

    def percentiles(self, q: tuple[float, ...] = (5, 25, 50, 75, 95)) -> pd.Series:
        """Percentiles of the final return.

        Args:
            q: Percentiles to compute, between 0 and 100.

        Returns:
            Final return at each percentile, indexed by q.
        """
        q = np.asarray(q, dtype=float)
        if ((q < 0) | (q > 100)).any():
            raise ValueError(f"q must be between 0 and 100, got {q.tolist()}")
        result = self.final_returns.quantile(q / 100)
        result.index = q
        return result

    def var(self, level: float = 0.95) -> float:
        """Loss not exceeded with probability level, as a positive return.

        A negative value means that even the worst simulations at that level
        end with a gain.
        """
        _check_level(level)
        return -float(self.final_returns.quantile(1 - level))

    def cvar(self, level: float = 0.95) -> float:
        """Mean loss in the simulations at or beyond the VaR, as a positive return."""
        returns = self.final_returns
        tail = returns[returns <= -self.var(level)]
        return -float(tail.mean())

    def loss_probability(self) -> float:
        """Share of simulations that end below the initial value."""
        return float((self.final_returns < 0).mean())

    def summary(self, levels: tuple[float, ...] = (0.95, 0.99)) -> dict[str, float]:
        """Mean, median, VaR and CVaR at each level, and loss probability."""
        data = {'mean': self.mean(), 'median': self.median()}
        for level in levels:
            label = f"{level * 100:g}"
            data[f'var_{label}'] = self.var(level)
            data[f'cvar_{label}'] = self.cvar(level)
        data['loss_probability'] = self.loss_probability()
        return data

    def plot(self, n_paths: int = 100, level: float = 0.95) -> np.ndarray:
        """Simulated paths and distribution of the final return.

        Left: a sample of paths with the median and the 5-95 percentile band.
        Right: histogram of the final return with the mean, VaR and CVaR.

        Args:
            n_paths: Number of paths drawn on the left (the first ones).
            level: Confidence level of the VaR and CVaR lines.

        Returns:
            The two matplotlib axes. In a script call plt.show() to see them.
        """
        if (
            isinstance(n_paths, bool)
            or not isinstance(n_paths, (int, np.integer))
            or n_paths <= 0
        ):
            raise ValueError(f"n_paths must be a positive integer, got {n_paths!r}")
        _check_level(level)

        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        years = self.paths.index / self.periods_per_year

        # 1. Paths and percentile band.
        ax = axes[0]
        ax.plot(years, self.paths.iloc[:, :n_paths], color='tab:blue', alpha=0.15, lw=0.8)
        bands = self.paths.quantile([0.05, 0.5, 0.95], axis=1).T
        ax.fill_between(years, bands[0.05], bands[0.95], color='tab:blue', alpha=0.15,
                        label='5-95 percentile')
        ax.plot(years, bands[0.5], color='black', lw=1.5, label='Median')
        ax.axhline(self.initial_value, color='grey', ls='--', lw=1)
        ax.set_title(f"Simulated values: {self.target} ({self.paths.shape[1]:,} paths)")
        ax.set_xlabel('Years')
        ax.set_ylabel('Value')
        ax.legend(loc='upper left')

        # 2. Distribution of the final return.
        ax = axes[1]
        label = f"{level * 100:g}%"
        ax.hist(self.final_returns, bins=60, color='tab:blue', alpha=0.7)
        ax.axvline(self.mean(), color='black', lw=1.5, label=f"Mean {self.mean():.1%}")
        ax.axvline(-self.var(level), color='tab:orange', lw=1.5,
                   label=f"VaR {label} {self.var(level):.1%}")
        ax.axvline(-self.cvar(level), color='tab:red', lw=1.5,
                   label=f"CVaR {label} {self.cvar(level):.1%}")
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title('Final return')
        ax.set_xlabel('Return over the horizon')
        ax.set_ylabel('Simulations')
        ax.legend()

        fig.tight_layout()
        return axes
