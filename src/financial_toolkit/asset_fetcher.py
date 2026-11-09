import os
from dataclasses import dataclass, field, replace

import pandas as pd

from .YahooFinanceAPI import YahooFinanceAPI
from .fmp_api import FMPAPI
from .coingeckoapi import CoinGeckoApi
from .us_treasury_api import USTreasuryAPI
from .bce_bond_api import BCEBondAPI
from .jp_bond_api import JapanBondAPI
from .uk_bond_api import UKBondAPI
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

    # Informe de limpieza de la última llamada a get_many, por símbolo.
    cleaning_reports: dict = field(default_factory=dict, init=False)

    def get_many(self, solicitudes, *, start, end):
        """recibe la lista, elige el buscador de cada activo y reúne los resultados. Este es el comportamiento que queremos de AssetFetcher."""
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

        if (
            pd.isna(start)
            or pd.isna(end)
            or start.tzinfo is not None
            or end.tzinfo is not None
        ):
            raise ValueError("Usa fechas válidas sin zona horaria")

        start = start.normalize()
        end = end.normalize()

        if start > end or end > today:
            raise ValueError(
                "Debe cumplirse start <= end y end no puede ser futura"
            )

        extractores = {
            ("stock", "yfinance"): self.yahoo.get_stock,
            ("index", "yfinance"): self.yahoo.get_index,
            ("stock", "fmp"): self.fmp.get_stock,
            ("index", "fmp"): self.fmp.get_index,
            ("crypto", "coingecko"): self.coingecko.get_crypto,
            ("bond", "us_treasury"): self.us_treasury.get_data,
            ("bond", "bce"): self.bce.get_data,
            ("bond", "japan"): self.japan.get_data,
            ("bond", "uk"): self.uk.get_data,
        }

        activos = []
        self.cleaning_reports = {}

        for solicitud in solicitudes:
            tipo = solicitud["type"].strip().lower()
            api = solicitud["api"].strip().lower()
            symbol = solicitud["symbol"].strip()
            clave = (tipo, api)

            if clave not in extractores:
                raise ValueError(f"Combinación no admitida: {clave}")

            if api == "fmp" and not self.fmp.api_key:
                raise ValueError("Falta FMP_API_KEY")

            parametros = self._parametros(
                tipo, api, symbol, start, end, today
            )

            opciones = solicitud.get("params", {})
            if not isinstance(opciones, dict):
                raise ValueError("params debe ser un diccionario")

            reservados = {
                "start", "end", "start_date", "end_date",
                "period", "days", "ticker", "symbol", "coin_id",
            }

            if reservados.intersection(opciones):
                raise ValueError(
                    "Indica el activo en symbol y el periodo "
                    "en start/end de get_many()"
                )

            activo = extractores[clave](**parametros, **opciones)

            if tipo == "bond":
                activo = self.bond_normalizer.normalize(
                    data=activo,
                    ticker=symbol,
                    source=api,
                    start_date=start,
                    end_date=end,
                )
            else:
                activo = self._recortar(activo, start, end)
                precios, informe = clean_prices(activo.price)
                activo = replace(activo, price=precios)
                self.cleaning_reports[symbol] = informe

            activos.append(activo)

        return activos

    @staticmethod
    def _parametros(tipo, api, symbol, start, end, today):
        """traduce las fechas porque nuestros buscadores usan argumentos distintos: period, start/end o days."""
        if tipo == "bond":
            return {
                "ticker": symbol,
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
            }

        if api == "coingecko":
            necesarios = (today - start).days + 1

            dias = next(
                (
                    ventana
                    for ventana in (1, 7, 14, 30, 90, 180, 365)
                    if ventana >= necesarios
                ),
                None,
            )

            if dias is None:
                raise ValueError(
                    "El extractor actual de CoinGecko no cubre "
                    "el inicio solicitado"
                )

            return {"coin_id": symbol, "days": dias}

        if api == "yfinance" and tipo == "index":
            return {
                "symbol": symbol,
                "start": start.strftime("%Y-%m-%d"),
                # Yahoo interpreta end como exclusivo.
                "end": (
                    end + pd.Timedelta(days=1)
                ).strftime("%Y-%m-%d"),
            }

        # Los métodos restantes reciben un periodo en años.
        years = max(1, today.year - start.year + 1)
        identificador = "ticker" if tipo == "stock" else "symbol"

        return {
            identificador: symbol,
            "period": f"{years}y",
        }

    @staticmethod
    def _recortar(activo, start, end):
        """limita los precios al intervalo elegido, porque algunos buscadores descargan un periodo más amplio.."""
        precios = activo.price
        indice = pd.DatetimeIndex(precios.close.index)
        fechas = indice.tz_localize(None).normalize()
        seleccion = (fechas >= start) & (fechas <= end)

        if not seleccion.any():
            raise ValueError(
                "No hay precios dentro del periodo solicitado"
            )

        campos = {
            nombre: (
                None
                if getattr(precios, nombre) is None
                else getattr(precios, nombre).iloc[seleccion].copy()
            )
            for nombre in ("open", "high", "low", "close", "volume")
        }

        precios_recortados = replace(
            precios,
            date=indice[seleccion],
            **campos,
        )

        return replace(activo, price=precios_recortados)