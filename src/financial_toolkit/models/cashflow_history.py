from dataclasses import dataclass, field, asdict
from .cashflow import CashFlow

import pandas as pd
import numpy as np


@dataclass
class CashFlowHistory:

    statements: list[CashFlow] = field(default_factory=list)

    def add(self, statement: CashFlow):
        self.statements.append(statement)

    def get_by_year(self, year: int) -> CashFlow | None:
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

    def analyze(self) -> pd.DataFrame:

        statements = sorted(
            self.statements,
            key=lambda x: x.date
        )

        col = len(statements)
        results = []

        def safe_division(numerator, denominator):
            if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
                return np.nan
            return numerator / denominator

        for i in range(0, col):

            actual = statements[i]

            year = actual.date.year

            # Cash flow consistency

            consistency = np.isclose(
                actual.operating_cash_flow
                + actual.investing_cash
                + actual.financing_cash_flow,
                actual.changes_cash
            )

            # Free cash flow

            fcf = (
                actual.operating_cash_flow
                - np.abs(actual.capital_expenditure)
            )

            # CAPEX ratios

            capex_da_ratio = (
                safe_division(
                    np.abs(actual.capital_expenditure),
                    np.abs(actual.depreciation_amortization)
                )
            )

            capex_cfo_ratio = (
                safe_division(
                    np.abs(actual.capital_expenditure),
                    actual.operating_cash_flow
                )
            )

            # Dividend coverage

            dividend_coverage = (
                safe_division(fcf, np.abs(actual.cash_dividends_paid))
            )

            # FCF payout ratio

            payout_fcf = safe_division(
                np.abs(actual.cash_dividends_paid)
                + np.abs(actual.repurchase_stock)
                if pd.notna(actual.cash_dividends_paid) and pd.notna(actual.repurchase_stock)
                else np.nan,
                fcf
            )

            # Net debt issued

            net_debt_issued = (
                (
                    actual.issuance_debt
                    if pd.notna(actual.issuance_debt)
                    else 0
                )
                +
                (
                    actual.repayment_debt
                    if pd.notna(actual.repayment_debt)
                    else 0
                )
            )

            # Working capital

            working_capital = safe_division(
                actual.change_working_capital, actual.operating_cash_flow
            ) * 100

            # Other investments

            other_investments = (
                actual.investing_cash
                + np.abs(actual.capital_expenditure)
            )

            # Reconstructed operating cash flow

            reconstructed_cfo = (
                actual.net_income_continuing_operations
                + np.abs(actual.depreciation_amortization)
                + actual.change_working_capital
            )

            # Difference between CFO and reconstructed CFO

            cfo_difference = (
                actual.operating_cash_flow
                - reconstructed_cfo
            )

            cfo_difference_percentage = safe_division(
                cfo_difference, reconstructed_cfo
            ) * 100

            # Other financing cash flows

            other_financing_cash_flows = (
                actual.financing_cash_flow
                -
                (
                    (
                        actual.issuance_debt
                        if pd.notna(actual.issuance_debt)
                        else 0
                    )
                    +
                    (
                        actual.repayment_debt
                        if pd.notna(actual.repayment_debt)
                        else 0
                    )
                    +
                    (
                        actual.repurchase_stock
                        if pd.notna(actual.repurchase_stock)
                        else 0
                    )
                    +
                    (
                        actual.cash_dividends_paid
                        if pd.notna(actual.cash_dividends_paid)
                        else 0
                    )
                )
            )

            # Warnings

            negative_fcf = fcf < 0

            dividend_coverage_below_one = (
                dividend_coverage < 1
            )

            capex_exceeds_da = (
                capex_da_ratio > 1
            )

            # Changes compared with previous year

            if i >= 1:

                previous = statements[i - 1]

                cfo_change = safe_division(
                    actual.operating_cash_flow - previous.operating_cash_flow,
                    previous.operating_cash_flow
                ) * 100

                previous_fcf = results[i - 1]["Free cash flow (FCF)"]
                fcf_change = safe_division(
                    fcf - previous_fcf, previous_fcf
                ) * 100

            else:

                cfo_change = np.nan
                fcf_change = np.nan

            results.append({

                "Year": year,

                "Consistency (CFO + CFI + CFF = Net cash change)":
                    consistency,

                "Free cash flow (FCF)":
                    fcf,

                "CAPEX/DA ratio":
                    capex_da_ratio,

                "CAPEX/CFO ratio":
                    capex_cfo_ratio,

                "Dividend coverage":
                    dividend_coverage,

                "FCF payout ratio":
                    payout_fcf,

                "Net debt issued":
                    net_debt_issued,

                "Working capital (%)":
                    working_capital,

                "Other investments":
                    other_investments,

                "Reconstructed CFO":
                    reconstructed_cfo,

                "CFO - Reconstructed CFO difference":
                    cfo_difference,

                "CFO - Reconstructed CFO difference (%)":
                    cfo_difference_percentage,

                "Other financing cash flows":
                    other_financing_cash_flows,

                "Negative FCF":
                    negative_fcf,

                "Dividend coverage below 1":
                    dividend_coverage_below_one,

                "CAPEX exceeds DA":
                    capex_exceeds_da,

                "CFO change (%)":
                    cfo_change,

                "FCF change (%)":
                    fcf_change
            })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)

        result_df = result_df.set_index("Year").T

        result_df.columns.name = None

        return result_df