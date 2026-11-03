import pandas as pd
import requests


class USTreasuryAPI:

    def get_data(self, ticker, start_date, end_date):
        inicio = pd.Timestamp(start_date)
        fin = pd.Timestamp(end_date)

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        url = (
            "https://home.treasury.gov/resource-center/"
            "data-chart-center/interest-rates/pages/xml"
        )

        respuestas = []

        with requests.Session() as session:
            for year in range(inicio.year, fin.year + 1):
                response = session.get(
                    url,
                    params={
                        "data": "daily_treasury_yield_curve",
                        "field_tdr_date_value": year,
                    },
                    timeout=30,
                )

                response.raise_for_status()
                respuestas.append(response.content)

        return respuestas