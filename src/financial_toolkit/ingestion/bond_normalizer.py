from io import StringIO
import xml.etree.ElementTree as ET

import pandas as pd

from ..models.bond import Bond
from ..models.bondseries import BondSeries


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

        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()

        if pd.isna(start) or pd.isna(end) or start > end:
            raise ValueError("Invalid date interval.")

        # 1. Parse the source format.
        if source == "us_treasury":
            table = self._from_us_treasury(data, ticker)

            country = "US"
            maturity = self.TREASURY_FIELDS[ticker][1]

            name = (
                f"US Treasury: {ticker[2:]} par yield "
                f"(USD)"
            )

        elif source == "bce":
            self._validate_ticker(
                ticker,
                self.BCE_MATURITIES,
            )

            table = self._from_bce(data)

            country = "U2"
            maturity = self.BCE_MATURITIES[ticker]

            name = (
                f"Euro area AAA: {ticker[2:]} par yield "
                f"(EUR)"
            )

        elif source == "japan":
            table = self._from_japan(data, ticker)

            country = "JP"
            maturity = self.JAPAN_FIELDS[ticker][1]

            name = (
                f"Japan JGB: {ticker[2:]} constant maturity yield "
                f"(JPY)"
            )

        elif source == "uk":
            table = self._from_uk(data, ticker)

            country = "GB"
            maturity = self.UK_FIELDS[ticker][1]

            name = (
                f"United Kingdom: {ticker[2:]} par yield "
                f"(GBP)"
            )

        else:
            raise ValueError(
                f"Unsupported source: {source}"
            )

        # 2. Convert dates and yields.
        table["date"] = pd.to_datetime(
            table["date"],
            errors="coerce",
        )

        table["ytm"] = pd.to_numeric(
            table["ytm"],
            errors="coerce",
        )

        table["ytm"] = table["ytm"].replace(
            [float("inf"), -float("inf")],
            float("nan"),
        )

        if table["date"].isna().any():
            raise ValueError(
                f"Missing or invalid dates "
                f"in {source} for {ticker}."
            )

        # 3. Filter dates and drop identical duplicates.
        table = (
            table.loc[
                table["date"].between(start, end)
            ]
            .drop_duplicates()
            .sort_values("date")
            .reset_index(drop=True)
        )

        if table.empty:
            raise ValueError(
                f"Insufficient data in {source} for "
                f"{ticker}: no records in the interval."
            )

        if table["date"].duplicated().any():
            raise ValueError(
                f"Different records for the same date "
                f"in {source} for {ticker}."
            )

        # 4. Check the missing values before dropping them.
        missing_ratio = table["ytm"].isna().mean()

        if missing_ratio > self.MAX_MISSING_RATIO:
            raise ValueError(
                f"Insufficient data in {source} for "
                f"{ticker}: {missing_ratio:.2%} of "
                f"missing yields. "
                f"Maximum allowed: "
                f"{self.MAX_MISSING_RATIO:.0%}."
            )

        table = table.dropna(
            subset=["ytm"]
        ).reset_index(drop=True)

        # 5. Build the series and the Bond object.
        dates = pd.DatetimeIndex(
            table["date"],
            name="date",
        )

        series = BondSeries(
            date=dates,
            ytm=pd.Series(
                table["ytm"].to_numpy(),
                index=dates,
                name=ticker,
            ),
        )

        return Bond(
            ticker=ticker,
            name=name,
            country=country,
            maturity_years=maturity,
            source=source,
            series=series,
        )

    def _validate_ticker(self, ticker, mapping):
        if ticker not in mapping:
            raise ValueError(
                f"Unsupported reference: {ticker}. "
                f"Available: {', '.join(mapping)}"
            )

    def _from_us_treasury(self, data, ticker):
        self._validate_ticker(
            ticker,
            self.TREASURY_FIELDS,
        )

        field = self.TREASURY_FIELDS[ticker][0]

        namespaces = {
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

        records = []

        for document in data:
            root = ET.fromstring(document)

            for entry in root.findall(
                "atom:entry",
                namespaces,
            ):
                properties = entry.find(
                    "atom:content/m:properties",
                    namespaces,
                )

                if properties is None:
                    raise ValueError(
                        "US Treasury record "
                        "without properties."
                    )

                date_node = properties.find(
                    "d:NEW_DATE",
                    namespaces,
                )

                yield_node = properties.find(
                    f"d:{field}",
                    namespaces,
                )

                records.append({
                    "date": (
                        date_node.text
                        if date_node is not None
                        else None
                    ),
                    "ytm": (
                        yield_node.text
                        if yield_node is not None
                        else None
                    ),
                })

        return pd.DataFrame(
            records,
            columns=["date", "ytm"],
        )

    def _from_bce(self, data):
        if not data or not data.strip():
            return pd.DataFrame(
                columns=["date", "ytm"]
            )

        table = pd.read_csv(StringIO(data))

        if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(
            table.columns
        ):
            raise ValueError(
                "ECB response without the columns "
                "TIME_PERIOD and OBS_VALUE."
            )

        return table[
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

        # The first line holds the title, not the header.
        table = pd.read_csv(
            StringIO(data),
            skiprows=1,
        )

        table.columns = table.columns.str.strip()

        field = self.JAPAN_FIELDS[ticker][0]

        if not {"Date", field}.issubset(table.columns):
            raise ValueError(
                f"Japan response without the columns "
                f"Date and {field}."
            )

        table = table[
            ["Date", field]
        ].rename(
            columns={
                "Date": "date",
                field: "ytm",
            }
        )

        table["date"] = pd.to_datetime(
            table["date"],
            format="%Y/%m/%d",
            errors="coerce",
        )

        return table

    def _from_uk(self, data, ticker):
        self._validate_ticker(
            ticker,
            self.UK_FIELDS,
        )

        if not data or not data.strip():
            return pd.DataFrame(
                columns=["date", "ytm"]
            )

        table = pd.read_csv(StringIO(data))

        table.columns = table.columns.str.strip()

        field = self.UK_FIELDS[ticker][0]

        if not {"DATE", field}.issubset(table.columns):
            raise ValueError(
                f"Bank of England response without the "
                f"columns DATE and {field}."
            )

        table = table[
            ["DATE", field]
        ].rename(
            columns={
                "DATE": "date",
                field: "ytm",
            }
        )

        table["date"] = pd.to_datetime(
            table["date"],
            format="%d %b %Y",
            errors="coerce",
        )

        return table