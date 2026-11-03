from io import StringIO
import xml.etree.ElementTree as ET

import pandas as pd

from bond import Bond
from bondseries import BondSeries


class BondNormalizer:

    TREASURY_FIELDS = {
        "US1M": ("BC_1MONTH", 1 / 12),
        "US2M": ("BC_2MONTH", 2 / 12),
        "US3M": ("BC_3MONTH", 3 / 12),
        "US4M": ("BC_4MONTH", 4 / 12),
        "US6M": ("BC_6MONTH", 6 / 12),
        "US1Y": ("BC_1YEAR", 1),
        "US2Y": ("BC_2YEAR", 2),
        "US3Y": ("BC_3YEAR", 3),
        "US5Y": ("BC_5YEAR", 5),
        "US7Y": ("BC_7YEAR", 7),
        "US10Y": ("BC_10YEAR", 10),
        "US20Y": ("BC_20YEAR", 20),
        "US30Y": ("BC_30YEAR", 30),
    }

    BCE_COUNTRIES = {
        "ES10Y": ("ES", "España"),
        "FR10Y": ("FR", "Francia"),
        "IT10Y": ("IT", "Italia"),
        "DE10Y": ("DE", "Alemania"),
    }

    def normalize(
        self,
        data,
        ticker,
        source,
        start_date,
        end_date,
    ):
        ticker = ticker.strip().upper()
        inicio = pd.Timestamp(start_date).normalize()
        fin = pd.Timestamp(end_date).normalize()

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        if source == "us_treasury":
            tabla = self._from_us_treasury(data, ticker)

            pais = "US"
            plazo = self.TREASURY_FIELDS[ticker][1]

            nombre = (
                f"US Treasury par yield reference {ticker[2:]}"
            )

        elif source == "bce":
            if ticker not in self.BCE_COUNTRIES:
                raise ValueError(
                    f"Referencia no admitida: {ticker}"
                )

            tabla = self._from_bce(data)

            pais, nombre_pais = self.BCE_COUNTRIES[ticker]
            plazo = 10

            nombre = (
                f"{nombre_pais}: referencia gubernamental "
                "a 10 años (mensual)"
            )

            # Las fechas del BCE representan meses completos.
            inicio = inicio.to_period("M").start_time
            fin = fin.to_period("M").start_time

        else:
            raise ValueError(
                f"Fuente no admitida: {source}"
            )

        # Limpieza común para ambas fuentes.
        tabla["date"] = pd.to_datetime(tabla["date"])

        tabla["ytm"] = pd.to_numeric(
            tabla["ytm"],
            errors="coerce",
        )

        tabla = (
            tabla.dropna(subset=["date", "ytm"])
            .loc[
                lambda df: df["date"].between(inicio, fin)
            ]
            .drop_duplicates(subset="date")
            .sort_values("date")
            .reset_index(drop=True)
        )

        if tabla.empty:
            return None

        fechas = pd.DatetimeIndex(
            tabla["date"],
            name="date",
        )

        serie = BondSeries(
            date=fechas,
            ytm=pd.Series(
                tabla["ytm"].to_numpy(),
                index=fechas,
                name=ticker,
            ),
        )

        return Bond(
            ticker=ticker,
            name=nombre,
            country=pais,
            maturity_years=plazo,
            source=source,
            series=serie,
        )

    def _from_us_treasury(self, data, ticker):
        if ticker not in self.TREASURY_FIELDS:
            raise ValueError(
                f"Referencia no admitida: {ticker}"
            )

        campo = self.TREASURY_FIELDS[ticker][0]

        espacios = {
            "atom": "http://www.w3.org/2005/Atom",
            "m": (
                "http://schemas.microsoft.com/ado/"
                "2007/08/dataservices/metadata"
            ),
            "d": (
                "http://schemas.microsoft.com/ado/"
                "2007/08/dataservices"
            ),
        }

        registros = []

        for documento in data:
            raiz = ET.fromstring(documento)

            for entrada in raiz.findall(
                "atom:entry",
                espacios,
            ):
                propiedades = entrada.find(
                    "atom:content/m:properties",
                    espacios,
                )

                if propiedades is None:
                    continue

                fecha = propiedades.find(
                    "d:NEW_DATE",
                    espacios,
                )

                rendimiento = propiedades.find(
                    f"d:{campo}",
                    espacios,
                )

                if fecha is None or rendimiento is None:
                    continue

                if not fecha.text or not rendimiento.text:
                    continue

                registros.append({
                    "date": fecha.text,
                    "ytm": rendimiento.text,
                })

        return pd.DataFrame(
            registros,
            columns=["date", "ytm"],
        )

    def _from_bce(self, data):
        if not data or not data.strip():
            return pd.DataFrame(
                columns=["date", "ytm"]
            )

        tabla = pd.read_csv(StringIO(data))

        return tabla[
            ["TIME_PERIOD", "OBS_VALUE"]
        ].rename(
            columns={
                "TIME_PERIOD": "date",
                "OBS_VALUE": "ytm",
            }
        )