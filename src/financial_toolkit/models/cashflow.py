from dataclasses import dataclass
from datetime import date


@dataclass
class CashFlow:
    date: date
    net_income_continuing_operations: float
    depreciation_amortization: float
    change_working_capital: float
    operating_cash_flow: float
    capital_expenditure: float
    investing_cash: float
    issuance_debt: float
    repayment_debt: float
    repurchase_stock: float
    cash_dividends_paid: float
    financing_cash_flow: float
    changes_cash: float