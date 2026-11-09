from dataclasses import dataclass, field

from .fundamentals import Fundamentals


@dataclass
class Company:
    name: str
    country: str
    industry: str
    fundamentals: Fundamentals = field(
        default_factory=Fundamentals
    )