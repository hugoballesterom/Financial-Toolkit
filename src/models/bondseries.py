from dataclasses import dataclass

import pandas as pd


@dataclass
class BondSeries:
    date: pd.DatetimeIndex
    ytm: pd.Series  # Porcentaje: 4.5 significa 4,5 %.

    def current_yield(self):
        return self.ytm.iloc[-1]

    def yield_change_bps(self):
        return self.ytm.diff() * 100

    def yield_max(self):
        return self.ytm.max()

    def yield_min(self):
        return self.ytm.min()
    
    def yield_mean(self):
        """Rentabilidad media del intervalo, en porcentaje."""
        return self.ytm.mean()

    def yield_change_total_bps(self):
        """Cambio entre la última y la primera rentabilidad, en puntos básicos."""
        return (self.ytm.iloc[-1] - self.ytm.iloc[0]) * 100

    def yield_volatility(self):
        """Desviación estándar muestral de las rentabilidades, en puntos porcentuales."""
        return self.ytm.std()