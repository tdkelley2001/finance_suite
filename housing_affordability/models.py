# housing_affordability/models.py

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MortgageAssumptions:
    interest_rate: float          # annual, e.g. 0.065
    term_years: int               # 15, 20, 30
    property_tax_rate: float      # annual % of home value
    annual_insurance: float       # dollars
    monthly_hoa: float            # dollars
    pmi_rate: float               # annual % of loan balance (0 if none)


@dataclass(frozen=True)
class Household:
    net_monthly_income: float
    non_housing_expenses: float
    planned_savings: float
    min_monthly_buffer: float


@dataclass(frozen=True)
class CashPosition:
    cash_available: float
    down_payment_pct: float
    closing_cost_pct: float
    reserve_requirement: float


@dataclass(frozen=True)
class AffordabilityConstraints:
    max_payment_ratio: float   # % of net income, e.g. 0.30


@dataclass(frozen=True)
class MonthlyHousingCost:
    principal_and_interest: float
    property_tax: float
    insurance: float
    hoa: float
    pmi: float

    @property
    def total(self) -> float:
        return (
            self.principal_and_interest
            + self.property_tax
            + self.insurance
            + self.hoa
            + self.pmi
        )


@dataclass(frozen=True)
class AffordabilityResult:
    max_home_price: float
    max_monthly_payment: float
    monthly_cost: MonthlyHousingCost
    binding_constraint: str
