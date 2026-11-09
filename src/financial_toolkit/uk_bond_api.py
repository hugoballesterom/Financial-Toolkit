import pandas as pd
import requests


class UKBondAPI:

    SERIES_MAP = {
        "UK5Y": "IUDSNPY",
        "UK10Y": "IUDMNPY",
        "UK20Y": "IUDLNPY",
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

        # The service needs the months written in English.
        months = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )

        start_text = (
            f"{start.day:02d}/"
            f"{months[start.month - 1]}/"
            f"{start.year}"
        )

        end_text = (
            f"{end.day:02d}/"
            f"{months[end.month - 1]}/"
            f"{end.year}"
        )

        url = (
            "https://www.bankofengland.co.uk/boeapps/database/"
            "_iadb-fromshowcolumns.asp"
        )

        response = requests.get(
            url,
            params={
                "csv.x": "yes",
                "Datefrom": start_text,
                "Dateto": end_text,
                "SeriesCodes": self.SERIES_MAP[ticker],
                "CSVF": "TN",
                "UsingCodes": "Y",
                "VPD": "Y",
                "VFD": "N",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
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