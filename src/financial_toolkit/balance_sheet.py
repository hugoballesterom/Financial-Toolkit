from dataclasses import dataclass
from datetime import date


@dataclass
class BalanceSheet:
    date: date
    cash_equivalents: float
    total_debt: float
    account_receivable: float
    inventory: float
    current_assets: float
    net_ppe: float
    goodwill_intangible: float
    total_assets: float
    current_liabilities: float
    long_term_debt: float
    total_liabilities: float
    stockholders_equity: float
    