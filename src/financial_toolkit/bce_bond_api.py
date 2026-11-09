import pandas as pd
import requests


class BCEBondAPI:

    SERIES_MAP = {
        "EU3M": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_3M",
        "EU4M": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_4M",
        "EU6M": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_6M",
        "EU1Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_1Y",
        "EU2Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_2Y",
        "EU3Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_3Y",
        "EU5Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_5Y",
        "EU7Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_7Y",
        "EU10Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_10Y",
        "EU20Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_20Y",
        "EU30Y": "B.U2.EUR.4F.G_N_A.SV_C_YM.PY_30Y",
    }

    def get_data(self, ticker, start_date, end_date):
        ticker = ticker.strip().upper()

        if ticker not in self.SERIES_MAP:
            raise ValueError(
                f"Unsupported reference: {ticker}. "
                f"Available: {', '.join(self.SERIES_MAP)}"
            )

        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()

        if pd.isna(start) or pd.isna(end) or start > end:
            raise ValueError("Invalid date interval.")

        key = self.SERIES_MAP[ticker]

        url = (
            "https://data-api.ecb.europa.eu/"
            f"service/data/YC/{key}"
        )

        response = requests.get(
            url,
            params={
                "startPeriod": start.strftime("%Y-%m-%d"),
                "endPeriod": end.strftime("%Y-%m-%d"),
                "format": "csvdata",
            },
            timeout=60,
        )

        response.raise_for_status()

        if response.status_code == 204:
            return ""

        response.encoding = "utf-8-sig"

        if response.text.lstrip().startswith("<"):
            raise ValueError(
                "The source returned HTML or XML "
                "instead of the CSV."
            )

        return response.text