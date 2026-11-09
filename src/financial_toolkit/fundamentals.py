from dataclasses import dataclass, field
import pandas as pd

from .income_statement_history import IncomeStatementHistory
from .balance_sheet_history import BalanceSheetHistory
from .cashflow_history import CashFlowHistory


@dataclass
class Fundamentals:
  
    income_statements: IncomeStatementHistory = field(
        default_factory=IncomeStatementHistory
    )

    balance_sheets: BalanceSheetHistory = field(
        default_factory=BalanceSheetHistory
    )

    cash_flows: CashFlowHistory = field(
        default_factory=CashFlowHistory
    )

    def analyze_income_statement(self) -> pd.DataFrame:
        return self.income_statements.analyze()

    def analyze_balance_sheet(self) -> pd.DataFrame:
        return self.balance_sheets.analyze()

    def analyze_cash_flow(self) -> pd.DataFrame:
        return self.cash_flows.analyze()

    def analyze(self) -> dict[str, pd.DataFrame]:
        return {
            "income_statement": self.analyze_income_statement(),
            "balance_sheet": self.analyze_balance_sheet(),
            "cash_flow": self.analyze_cash_flow()
        }