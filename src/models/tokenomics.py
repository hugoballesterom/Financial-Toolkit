from dataclasses import dataclass, field
import pandas as pd
from typing import Optional

@dataclass
class Tokenomics:
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    max_supply: Optional[float] = None
