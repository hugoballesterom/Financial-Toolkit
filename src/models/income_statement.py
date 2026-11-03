from dataclasses import dataclass
from datetime import date


@dataclass
class IncomeStatement:
    date: date
    total_revenue: float
    cost_revenue: float
    gross_profit: float
    operating_expense: float
    operating_income: float
    interest_expense: float
    pretax_income: float
    tax_provision: float
    net_income: float