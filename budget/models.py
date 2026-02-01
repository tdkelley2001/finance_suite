from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


SCHEMA_VERSION = 1


@dataclass
class SavingsItem:
    name: str
    monthly_amount: float


@dataclass
class BudgetAssumptions:
    net_monthly_income: float
    savings: List[SavingsItem] = field(default_factory=list)


@dataclass
class BudgetExpense:
    category: str
    subcategory: str
    monthly_amount: float
    required: bool


@dataclass
class BudgetMetadata:
    profile_id: Optional[str] = None
    user_id: Optional[str] = None
    name: str = "Default Budget"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BudgetProfile:
    schema_version: int = SCHEMA_VERSION
    metadata: BudgetMetadata = field(default_factory=BudgetMetadata)
    assumptions: BudgetAssumptions = field(default_factory=BudgetAssumptions)
    expenses: List[BudgetExpense] = field(default_factory=list)