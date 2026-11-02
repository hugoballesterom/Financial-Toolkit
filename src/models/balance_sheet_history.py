from dataclasses import dataclass, field, asdict
from balance_sheet import BalanceSheet

import pandas as pd
import numpy as np


@dataclass
class BalanceSheetHistory:

    statements: list[BalanceSheet] = field(default_factory=list)

    def add(self, statement: BalanceSheet):
        self.statements.append(statement)

    def get_by_year(self, year: int) -> BalanceSheet | None:
        for statement in self.statements:
            if statement.date.year == year:
                return statement
        return None

    def to_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame([
            asdict(statement) for statement in self.statements
        ])
        if df.empty:
            return df
        return df.set_index("date").T

    def analyze(self) -> pd.DataFrame:

        statements = sorted(
            self.statements,
            key=lambda x: x.date
        )

        col = len(statements)
        results = []

        def safe_division(numerator, denominator):
            if (
                pd.isna(numerator)
                or pd.isna(denominator)
                or denominator <= 0
            ):
                return np.nan

            return numerator / denominator

        for i in range(0, col):

            actual = statements[i]

            year = actual.date.year

            # Ratios and asset composition

            debt_to_equity = safe_division(
                actual.total_debt,
                actual.stockholders_equity
            )

            current_assets_weight = safe_division(
                actual.current_assets,
                actual.total_assets
            ) * 100

            inventory_weight = safe_division(
                actual.inventory,
                actual.total_assets
            ) * 100

            net_ppe_weight = safe_division(
                actual.net_ppe,
                actual.total_assets
            ) * 100

            intangible_assets_weight = safe_division(
                actual.goodwill_intangible,
                actual.total_assets
            ) * 100

            debt_to_liabilities_weight = safe_division(
                actual.total_debt,
                actual.total_liabilities
            ) * 100

            # Balance sheet consistency

            assets = actual.total_assets
            liabilities = actual.total_liabilities
            equity = actual.stockholders_equity

            if (
                pd.isna(assets)
                or pd.isna(liabilities)
                or pd.isna(equity)
            ):
                consistency = pd.NA

            else:
                consistency = np.isclose(
                    assets,
                    liabilities + equity
                )

            # Negative equity warning

            negative_equity = (
                actual.stockholders_equity <= 0
                if not pd.isna(actual.stockholders_equity)
                else pd.NA
            )

            # Changes compared with previous year

            if i >= 1:

                previous = statements[i - 1]

                inventory_change = safe_division(
                    actual.inventory - previous.inventory,
                    previous.inventory
                ) * 100

                net_ppe_change = safe_division(
                    actual.net_ppe - previous.net_ppe,
                    previous.net_ppe
                ) * 100

                total_assets_change_percentage = safe_division(
                    actual.total_assets - previous.total_assets,
                    previous.total_assets
                ) * 100

                cash_change = safe_division(
                    actual.cash_equivalents - previous.cash_equivalents,
                    previous.cash_equivalents
                ) * 100

                receivables_change = safe_division(
                    actual.account_receivable - previous.account_receivable,
                    previous.account_receivable
                ) * 100

                intangible_assets_change = safe_division(
                    actual.goodwill_intangible - previous.goodwill_intangible,
                    previous.goodwill_intangible
                ) * 100

                debt_change_percentage = safe_division(
                    actual.total_debt - previous.total_debt,
                    previous.total_debt
                ) * 100

                equity_change_percentage = safe_division(
                    actual.stockholders_equity - previous.stockholders_equity,
                    previous.stockholders_equity
                ) * 100

                # Absolute changes

                total_assets_change = (
                    actual.total_assets - previous.total_assets
                )

                debt_change = (
                    actual.total_debt - previous.total_debt
                )

                equity_change = (
                    actual.stockholders_equity
                    - previous.stockholders_equity
                )

                other_liabilities_current = (
                    actual.total_liabilities - actual.total_debt
                )

                other_liabilities_previous = (
                    previous.total_liabilities - previous.total_debt
                )

                other_liabilities_change = (
                    other_liabilities_current
                    - other_liabilities_previous
                )

                # Change in debt-to-equity ratio

                debt_to_equity_change = (
                    debt_to_equity
                    - results[i - 1]["Debt-to-equity ratio"]
                )

            else:

                inventory_change = np.nan
                net_ppe_change = np.nan
                total_assets_change_percentage = np.nan
                cash_change = np.nan
                receivables_change = np.nan
                intangible_assets_change = np.nan
                debt_change_percentage = np.nan
                equity_change_percentage = np.nan

                total_assets_change = np.nan
                debt_change = np.nan
                equity_change = np.nan
                other_liabilities_change = np.nan
                debt_to_equity_change = np.nan

            results.append({

                "Year": year,

                # Ratios and weights

                "Debt-to-equity ratio":
                    debt_to_equity,

                "Current assets weight (%)":
                    current_assets_weight,

                "Inventory weight (%)":
                    inventory_weight,

                "Net PPE weight (%)":
                    net_ppe_weight,

                "Intangible assets weight (%)":
                    intangible_assets_weight,

                "Debt-to-liabilities weight (%)":
                    debt_to_liabilities_weight,

                "Balance sheet consistency":
                    consistency,

                "Negative equity warning":
                    negative_equity,

                # Percentage changes

                "Inventory change (%)":
                    inventory_change,

                "Net PPE change (%)":
                    net_ppe_change,

                "Total assets change (%)":
                    total_assets_change_percentage,

                "Cash change (%)":
                    cash_change,

                "Accounts receivable change (%)":
                    receivables_change,

                "Intangible assets change (%)":
                    intangible_assets_change,

                "Debt change (%)":
                    debt_change_percentage,

                "Equity change (%)":
                    equity_change_percentage,

                # Absolute changes

                "Total assets change":
                    total_assets_change,

                "Debt change":
                    debt_change,

                "Other liabilities change":
                    other_liabilities_change,

                "Equity change":
                    equity_change,

                # Ratio change

                "Debt-to-equity change":
                    debt_to_equity_change
            })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)

        result_df["Balance sheet consistency"] = (
            result_df["Balance sheet consistency"].astype("boolean")
        )

        result_df["Negative equity warning"] = (
            result_df["Negative equity warning"].astype("boolean")
        )

        result_df = result_df.set_index("Year").T

        result_df.columns.name = None

        return result_df