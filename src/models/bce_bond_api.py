import pandas as pd
import requests


class BCEBondAPI:

    SERIES_MAP = {
        "ES10Y": "M.ES.L.L40.CI.0000.EUR.N.Z",
        "FR10Y": "M.FR.L.L40.CI.0000.EUR.N.Z",
        "IT10Y": "M.IT.L.L40.CI.0000.EUR.N.Z",
        "DE10Y": "M.DE.L.L40.CI.0000.EUR.N.Z",
    }

    def get_data(self, ticker, start_date, end_date):
        ticker = ticker.strip().upper()

        if ticker not in self.SERIES_MAP:
            raise ValueError(
                f"Referencia no admitida: {ticker}"
            )

        inicio = pd.Timestamp(start_date)
        fin = pd.Timestamp(end_date)

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        clave = self.SERIES_MAP[ticker]

        url = (
            "https://data-api.ecb.europa.eu/"
            f"service/data/IRS/{clave}"
        )

        response = requests.get(
            url,
            params={
                "startPeriod": inicio.strftime("%Y-%m"),
                "endPeriod": fin.strftime("%Y-%m"),
                "format": "csvdata",
            },
            timeout=60,
        )

        response.raise_for_status()

        if response.status_code == 204:
            return ""

        return response.text