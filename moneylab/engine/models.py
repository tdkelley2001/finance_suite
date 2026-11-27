"""Financial domain models with no application-framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_SCENARIO = "Current"
DEFAULT_GLOBAL_ASSUMPTIONS = {
    "inflation": 0.025, "expected_portfolio_return": 0.07,
    "expected_portfolio_volatility": 0.15, "cash_return": 0.04,
    "mortgage_rate": 0.065, "property_tax_rate": 0.012,
    "homeowners_insurance_annual": 1500.0, "pmi_rate": 0.01,
    "home_appreciation": 0.03, "rent_growth": 0.03,
    "default_tax_rate": 0.22, "capital_gains_tax_rate": 0.15,
    "default_withdrawal_rate": 0.04, "planning_horizon_years": 30,
    "recommended_emergency_months": 6,
}

@dataclass
class DataProvenance:
    source_type: str = "manual"
    source_id: str = ""
    label: str = ""
    updated_at: str = ""

@dataclass
class MonthlyCashFlowState:
    net_monthly_income: float = 0.0
    required_monthly_expenses: float = 0.0
    discretionary_monthly_expenses: float = 0.0
    planned_monthly_savings: float = 0.0
    savings_rate: float = 0.0
    emergency_expense_baseline: float = 0.0
    min_monthly_buffer: float = 500.0
    source: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

    @property
    def non_housing_expenses(self) -> float:
        return self.required_monthly_expenses + self.discretionary_monthly_expenses

@dataclass
class FinancialAccount:
    name: str
    account_type: str
    balance: float = 0.0
    tax_treatment: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class Asset:
    name: str
    asset_type: str
    value: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class Liability:
    name: str
    liability_type: str
    balance: float = 0.0
    payment: float = 0.0
    interest_rate: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class BalanceSheetState:
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    net_worth: float = 0.0
    liquid_assets: float = 0.0
    retirement_assets: float = 0.0
    taxable_assets: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class FinancialGoal:
    name: str
    goal_type: str
    target_amount: float = 0.0
    target_date: str = ""
    priority: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class ProfileState:
    monthly_cash_flow: MonthlyCashFlowState = field(default_factory=MonthlyCashFlowState)
    accounts: list[FinancialAccount] = field(default_factory=list)
    balance_sheet: BalanceSheetState = field(default_factory=BalanceSheetState)
    assets: list[Asset] = field(default_factory=list)
    liabilities: list[Liability] = field(default_factory=list)
    goals: list[FinancialGoal] = field(default_factory=list)

@dataclass
class AssumptionsState:
    global_defaults: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_GLOBAL_ASSUMPTIONS))
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class Scenario:
    name: str = DEFAULT_SCENARIO
    description: str = ""
    assumptions_overrides: dict[str, Any] = field(default_factory=dict)
    tool_inputs: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

@dataclass
class ScenariosState:
    active: str = DEFAULT_SCENARIO
    items: dict[str, Scenario] = field(default_factory=lambda: {DEFAULT_SCENARIO: Scenario()})

@dataclass
class ToolOutputsState:
    outputs: dict[str, Any] = field(default_factory=dict)

@dataclass
class UserState:
    updated_at: str = ""
    profile: ProfileState = field(default_factory=ProfileState)
    assumptions: AssumptionsState = field(default_factory=AssumptionsState)
    scenarios: ScenariosState = field(default_factory=ScenariosState)
    tool_outputs: ToolOutputsState = field(default_factory=ToolOutputsState)

    @property
    def cash_flow(self) -> MonthlyCashFlowState:
        return self.profile.monthly_cash_flow

SharedCashFlowState = MonthlyCashFlowState
