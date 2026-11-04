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

    BCE_MATURITIES = {
        "EU3M": 3 / 12,
        "EU4M": 4 / 12,
        "EU6M": 6 / 12,
        "EU1Y": 1,
        "EU2Y": 2,
        "EU3Y": 3,
        "EU5Y": 5,
        "EU7Y": 7,
        "EU10Y": 10,
        "EU20Y": 20,
        "EU30Y": 30,
    }

    JAPAN_FIELDS = {
        "JP1Y": ("1Y", 1),
        "JP2Y": ("2Y", 2),
        "JP3Y": ("3Y", 3),
        "JP4Y": ("4Y", 4),
        "JP5Y": ("5Y", 5),
        "JP6Y": ("6Y", 6),
        "JP7Y": ("7Y", 7),
        "JP8Y": ("8Y", 8),
        "JP9Y": ("9Y", 9),
        "JP10Y": ("10Y", 10),
        "JP15Y": ("15Y", 15),
        "JP20Y": ("20Y", 20),
        "JP25Y": ("25Y", 25),
        "JP30Y": ("30Y", 30),
        "JP40Y": ("40Y", 40),
    }

    UK_FIELDS = {
        "UK5Y": ("IUDSNPY", 5),
        "UK10Y": ("IUDMNPY", 10),
        "UK20Y": ("IUDLNPY", 20),
    }

    MAX_MISSING_RATIO = 0.05

    def normalize(
        self,
        data,
        ticker,
        source,
        start_date,
        end_date,
    ):
        ticker = ticker.strip().upper()
        source = source.strip().lower()

        inicio = pd.Timestamp(start_date).normalize()
        fin = pd.Timestamp(end_date).normalize()

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        # 1. Interpretar el formato de la fuente.
        if source == "us_treasury":
            tabla = self._from_us_treasury(data, ticker)

            pais = "US"
            plazo = self.TREASURY_FIELDS[ticker][1]

            nombre = (
                f"US Treasury: rentabilidad a la par "
                f"a {ticker[2:]} (USD)"
            )

        elif source == "bce":
            self._validate_ticker(
                ticker,
                self.BCE_MATURITIES,
            )

            tabla = self._from_bce(data)

            pais = "U2"
            plazo = self.BCE_MATURITIES[ticker]

            nombre = (
                f"Zona euro AAA: rentabilidad a la par "
                f"a {ticker[2:]} (EUR)"
            )

        elif source == "japan":
            tabla = self._from_japan(data, ticker)

            pais = "JP"
            plazo = self.JAPAN_FIELDS[ticker][1]

            nombre = (
                f"Japón JGB: rentabilidad a plazo constante "
                f"a {ticker[2:]} (JPY)"
            )

        elif source == "uk":
            tabla = self._from_uk(data, ticker)

            pais = "GB"
            plazo = self.UK_FIELDS[ticker][1]

            nombre = (
                f"Reino Unido: rentabilidad a la par "
                f"a {ticker[2:]} (GBP)"
            )

        else:
            raise ValueError(
                f"Fuente no admitida: {source}"
            )

        # 2. Convertir fechas y rentabilidades.
        tabla["date"] = pd.to_datetime(
            tabla["date"],
            errors="coerce",
        )

        tabla["ytm"] = pd.to_numeric(
            tabla["ytm"],
            errors="coerce",
        )

        tabla["ytm"] = tabla["ytm"].replace(
            [float("inf"), -float("inf")],
            float("nan"),
        )

        if tabla["date"].isna().any():
            raise ValueError(
                f"Fechas ausentes o inválidas "
                f"en {source} para {ticker}."
            )

        # 3. Filtrar fechas y eliminar duplicados idénticos.
        tabla = (
            tabla.loc[
                tabla["date"].between(inicio, fin)
            ]
            .drop_duplicates()
            .sort_values("date")
            .reset_index(drop=True)
        )

        if tabla.empty:
            raise ValueError(
                f"Datos insuficientes en {source} para "
                f"{ticker}: no hay registros en el intervalo."
            )

        if tabla["date"].duplicated().any():
            raise ValueError(
                f"Registros distintos para una misma fecha "
                f"en {source} para {ticker}."
            )

        # 4. Comprobar los nulos antes de eliminarlos.
        proporcion_nulos = tabla["ytm"].isna().mean()

        if proporcion_nulos > self.MAX_MISSING_RATIO:
            raise ValueError(
                f"Datos insuficientes en {source} para "
                f"{ticker}: {proporcion_nulos:.2%} de "
                f"rentabilidades nulas. "
                f"Máximo permitido: "
                f"{self.MAX_MISSING_RATIO:.0%}."
            )

        tabla = tabla.dropna(
            subset=["ytm"]
        ).reset_index(drop=True)

        # 5. Construir la serie y el objeto Bond.
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

    def _validate_ticker(self, ticker, mapping):
        if ticker not in mapping:
            raise ValueError(
                f"Referencia no admitida: {ticker}. "
                f"Disponibles: {', '.join(mapping)}"
            )

    def _from_us_treasury(self, data, ticker):
        self._validate_ticker(
            ticker,
            self.TREASURY_FIELDS,
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
                    raise ValueError(
                        "Registro de US Treasury "
                        "sin propiedades."
                    )

                fecha = propiedades.find(
                    "d:NEW_DATE",
                    espacios,
                )

                rendimiento = propiedades.find(
                    f"d:{campo}",
                    espacios,
                )

                registros.append({
                    "date": (
                        fecha.text
                        if fecha is not None
                        else None
                    ),
                    "ytm": (
                        rendimiento.text
                        if rendimiento is not None
                        else None
                    ),
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

        if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(
            tabla.columns
        ):
            raise ValueError(
                "Respuesta del BCE sin las columnas "
                "TIME_PERIOD y OBS_VALUE."
            )

        return tabla[
            ["TIME_PERIOD", "OBS_VALUE"]
        ].rename(
            columns={
                "TIME_PERIOD": "date",
                "OBS_VALUE": "ytm",
            }
        )

    def _from_japan(self, data, ticker):
        self._validate_ticker(
            ticker,
            self.JAPAN_FIELDS,
        )

        if not data or not data.strip():
            return pd.DataFrame(
                columns=["date", "ytm"]
            )

        # La primera línea contiene el título, no la cabecera.
        tabla = pd.read_csv(
            StringIO(data),
            skiprows=1,
        )

        tabla.columns = tabla.columns.str.strip()

        campo = self.JAPAN_FIELDS[ticker][0]

        if not {"Date", campo}.issubset(tabla.columns):
            raise ValueError(
                f"Respuesta de Japón sin las columnas "
                f"Date y {campo}."
            )

        tabla = tabla[
            ["Date", campo]
        ].rename(
            columns={
                "Date": "date",
                campo: "ytm",
            }
        )

        tabla["date"] = pd.to_datetime(
            tabla["date"],
            format="%Y/%m/%d",
            errors="coerce",
        )

        return tabla

    def _from_uk(self, data, ticker):
        self._validate_ticker(
            ticker,
            self.UK_FIELDS,
        )

        if not data or not data.strip():
            return pd.DataFrame(
                columns=["date", "ytm"]
            )

        tabla = pd.read_csv(StringIO(data))

        tabla.columns = tabla.columns.str.strip()

        campo = self.UK_FIELDS[ticker][0]

        if not {"DATE", campo}.issubset(tabla.columns):
            raise ValueError(
                f"Respuesta de Bank of England sin las "
                f"columnas DATE y {campo}."
            )

        tabla = tabla[
            ["DATE", campo]
        ].rename(
            columns={
                "DATE": "date",
                campo: "ytm",
            }
        )

        tabla["date"] = pd.to_datetime(
            tabla["date"],
            format="%d %b %Y",
            errors="coerce",
        )

        return tabla