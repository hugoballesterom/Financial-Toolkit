import pandas as pd
import requests


class JapanBondAPI:

    SERIES_MAP = {
        "JP1Y": "1Y",
        "JP2Y": "2Y",
        "JP3Y": "3Y",
        "JP4Y": "4Y",
        "JP5Y": "5Y",
        "JP6Y": "6Y",
        "JP7Y": "7Y",
        "JP8Y": "8Y",
        "JP9Y": "9Y",
        "JP10Y": "10Y",
        "JP15Y": "15Y",
        "JP20Y": "20Y",
        "JP25Y": "25Y",
        "JP30Y": "30Y",
        "JP40Y": "40Y",
    }

    def get_data(self, ticker, start_date, end_date):
        ticker = ticker.strip().upper()

        if ticker not in self.SERIES_MAP:
            raise ValueError(
                f"Referencia no admitida: {ticker}. "
                f"Disponibles: {', '.join(self.SERIES_MAP)}"
            )

        inicio = pd.Timestamp(start_date).normalize()
        fin = pd.Timestamp(end_date).normalize()

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        # Esta fuente entrega todos los plazos y todo el histórico.
        url = (
            "https://www.mof.go.jp/english/policy/jgbs/reference/"
            "interest_rate/historical/jgbcme_all.csv"
        )

        response = requests.get(
            url,
            timeout=60,
        )

        response.raise_for_status()

        if response.status_code == 204:
            return ""

        response.encoding = "utf-8-sig"

        if response.text.lstrip().startswith("<"):
            raise ValueError(
                "La fuente devolvió HTML o XML "
                "en lugar del CSV."
            )

        return response.text