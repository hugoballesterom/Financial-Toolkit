from enum import StrEnum


class Frequency(StrEnum):
    """Standard data frequencies used across the toolkit."""

    DAILY = 'D'
    WEEKLY = 'W'
    BIWEEKLY = 'BW'
    MONTHLY = 'M'
    QUARTERLY = 'Q'
    SEMIANNUAL = 'S'
    YEARLY = 'Y'