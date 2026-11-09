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
                f"Referencia no admitida: {ticker}. "
                f"Disponibles: {', '.join(self.SERIES_MAP)}"
            )

        inicio = pd.Timestamp(start_date).normalize()
        fin = pd.Timestamp(end_date).normalize()

        if pd.isna(inicio) or pd.isna(fin) or inicio > fin:
            raise ValueError("Intervalo de fechas no válido.")

        # El servicio necesita los meses escritos en inglés.
        meses = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )

        fecha_inicio = (
            f"{inicio.day:02d}/"
            f"{meses[inicio.month - 1]}/"
            f"{inicio.year}"
        )

        fecha_fin = (
            f"{fin.day:02d}/"
            f"{meses[fin.month - 1]}/"
            f"{fin.year}"
        )

        url = (
            "https://www.bankofengland.co.uk/boeapps/database/"
            "_iadb-fromshowcolumns.asp"
        )

        response = requests.get(
            url,
            params={
                "csv.x": "yes",
                "Datefrom": fecha_inicio,
                "Dateto": fecha_fin,
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
                "La fuente devolvió HTML o XML "
                "en lugar del CSV."
            )

        return response.text