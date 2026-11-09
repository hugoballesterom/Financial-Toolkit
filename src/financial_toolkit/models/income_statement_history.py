from dataclasses import dataclass, field, asdict
from .income_statement import IncomeStatement
import pandas as pd
import numpy as np


@dataclass
class IncomeStatementHistory:
    statements: list[IncomeStatement] = field(default_factory=list)

    def add(self, statement: IncomeStatement):
        self.statements.append(statement)

    def get_by_year(self, year: int) -> IncomeStatement | None:
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

        statements = sorted(self.statements, key=lambda x: x.date)

        col = len(statements)
        results = []

        for i in range(0, col):

            actual = statements[i]

            year = actual.date.year

            gross_margin_percentage = (
                (actual.total_revenue - actual.cost_revenue)
                / actual.total_revenue
            ) * 100

            operating_margin_percentage = (
                actual.operating_income
                / actual.total_revenue
            ) * 100

            operating_expense_to_revenue = (
                actual.operating_expense
                / actual.total_revenue
            ) * 100

            consistency = np.isclose(
                actual.gross_profit - actual.operating_expense,
                actual.operating_income
            )

            if i >= 1:

                previous = statements[i - 1]

                revenue_growth = (
                    (actual.total_revenue - previous.total_revenue)
                    / previous.total_revenue
                ) * 100

                cost_revenue_growth = (
                    (actual.cost_revenue - previous.cost_revenue)
                    / previous.cost_revenue
                ) * 100

                operating_expense_growth = (
                    (actual.operating_expense - previous.operating_expense)
                    / previous.operating_expense
                ) * 100

                operating_income_growth = (
                    (actual.operating_income - previous.operating_income)
                    / previous.operating_income
                ) * 100

                net_income_growth = (
                    (actual.net_income - previous.net_income)
                    / previous.net_income
                ) * 100

                interest_expense_growth = (
                    (actual.interest_expense - previous.interest_expense)
                    / previous.interest_expense
                ) * 100

                cost_revenue_warning = (
                    cost_revenue_growth > revenue_growth
                )

                operating_expense_warning = (
                    operating_expense_growth > revenue_growth
                )

            else:

                revenue_growth = np.nan
                cost_revenue_growth = np.nan
                operating_expense_growth = np.nan
                operating_income_growth = np.nan
                net_income_growth = np.nan
                interest_expense_growth = np.nan

                cost_revenue_warning = np.nan
                operating_expense_warning = np.nan

            results.append({
                "Year": year,

                "Gross margin percentage":
                    gross_margin_percentage,

                "Operating margin percentage":
                    operating_margin_percentage,

                "Operating expense to revenue":
                    operating_expense_to_revenue,

                "Consistency (Gross profit - operating expenses = operating income)":
                    consistency,

                "Revenue growth":
                    revenue_growth,

                "Cost of revenue growth":
                    cost_revenue_growth,

                "Operating expense growth":
                    operating_expense_growth,

                "Operating income growth":
                    operating_income_growth,

                "Net income growth":
                    net_income_growth,

                "Interest expense growth":
                    interest_expense_growth,

                "Warning: cost of revenue grows faster than revenue":
                    cost_revenue_warning,

                "Warning: operating expenses grow faster than revenue":
                    operating_expense_warning
            })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)

        result_df = result_df.set_index("Year").T

        result_df.columns.name = None

        return result_df

