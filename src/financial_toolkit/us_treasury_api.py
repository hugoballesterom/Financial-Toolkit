import pandas as pd
import requests


class USTreasuryAPI:

    SERIES_MAP = {
        "US1M": "BC_1MONTH",
        "US2M": "BC_2MONTH",
        "US3M": "BC_3MONTH",
        "US4M": "BC_4MONTH",
        "US6M": "BC_6MONTH",
        "US1Y": "BC_1YEAR",
        "US2Y": "BC_2YEAR",
        "US3Y": "BC_3YEAR",
        "US5Y": "BC_5YEAR",
        "US7Y": "BC_7YEAR",
        "US10Y": "BC_10YEAR",
        "US20Y": "BC_20YEAR",
        "US30Y": "BC_30YEAR",
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

        url = (
            "https://home.treasury.gov/resource-center/"
            "data-chart-center/interest-rates/pages/xml"
        )

        respuestas = []

        # Esta fuente entrega un XML por año con todos los plazos.
        for year in range(inicio.year, fin.year + 1):
            response = requests.get(
                url,
                params={
                    "data": "daily_treasury_yield_curve",
                    "field_tdr_date_value": year,
                },
                timeout=60,
            )

            response.raise_for_status()

            if response.status_code != 204 and response.content.strip():
                respuestas.append(response.content)

        return respuestas