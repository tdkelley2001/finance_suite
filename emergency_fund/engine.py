from __future__ import annotations

from dataclasses import dataclass

from net_worth.engine import effective_tax_treatment
from suite.state import FinancialAccount


CASH_ACCOUNT_TYPES = {"Cash", "Checking", "Savings", "Money Market"}


@dataclass(frozen=True)
class EmergencyFundInputs:
    monthly_required_expenses: float
    monthly_total_expenses: float
    monthly_net_income: float
    cash_balance: float
    liquid_assets: float
    recommended_months: float
    expense_basis: str = "required"


@dataclass(frozen=True)
class EmergencyFundResult:
    target_emergency_fund: float
    current_coverage_months: float
    gap_surplus: float
    recommended_months: float
    monthly_expense_basis: float
    expense_basis: str
    cash_balance: float
    liquid_assets: float
    liquid_asset_coverage_months: float


def cash_balance_from_accounts(accounts: list[FinancialAccount]) -> float:
    return sum(
        account.balance
        for account in accounts
        if account.account_type in CASH_ACCOUNT_TYPES
        or effective_tax_treatment(account) == "Cash"
    )


def calculate_emergency_fund(inputs: EmergencyFundInputs) -> EmergencyFundResult:
    monthly_expense_basis = _monthly_expense_basis(inputs)
    target = monthly_expense_basis * max(inputs.recommended_months, 0)
    current_coverage = _safe_months(inputs.cash_balance, monthly_expense_basis)
    liquid_asset_coverage = _safe_months(inputs.liquid_assets, monthly_expense_basis)

    return EmergencyFundResult(
        target_emergency_fund=target,
        current_coverage_months=current_coverage,
        gap_surplus=inputs.cash_balance - target,
        recommended_months=inputs.recommended_months,
        monthly_expense_basis=monthly_expense_basis,
        expense_basis=inputs.expense_basis,
        cash_balance=inputs.cash_balance,
        liquid_assets=inputs.liquid_assets,
        liquid_asset_coverage_months=liquid_asset_coverage,
    )


def _monthly_expense_basis(inputs: EmergencyFundInputs) -> float:
    if inputs.expense_basis == "total":
        return max(inputs.monthly_total_expenses, 0)
    return max(inputs.monthly_required_expenses, 0)


def _safe_months(balance: float, monthly_expense: float) -> float:
    if monthly_expense <= 0:
        return 0.0
    return max(balance, 0) / monthly_expense
