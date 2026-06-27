from dataclasses import dataclass
from typing import Dict
from .models import BudgetProfile
from suite.calculations import cash_flow_snapshot


@dataclass
class BudgetSummary:
    net_monthly_income: float
    total_savings: float
    savings_rate: float
    total_expenses: float
    required_expenses: float
    discretionary_expenses: float
    emergency_expense_baseline: float
    buffer: float
    expense_breakdown_by_category: Dict[str, float]


def calculate_budget_summary(profile: BudgetProfile) -> BudgetSummary:
    income = profile.assumptions.net_monthly_income

    total_savings = sum(
        s.monthly_amount for s in profile.assumptions.savings
    )
    savings_rate = total_savings / income if income > 0 else 0.0

    total_expenses = sum(
        e.monthly_amount for e in profile.expenses
    )

    required_expenses = sum(
        e.monthly_amount for e in profile.expenses if e.required
    )

    discretionary_expenses = total_expenses - required_expenses
    emergency_expense_baseline = required_expenses
    cash_flow = cash_flow_snapshot(
        income=income,
        required_expenses=required_expenses,
        discretionary_expenses=discretionary_expenses,
        savings=total_savings,
    )

    expense_breakdown_by_category: Dict[str, float] = {}
    for e in profile.expenses:
        expense_breakdown_by_category.setdefault(e.category, 0.0)
        expense_breakdown_by_category[e.category] += e.monthly_amount

    return BudgetSummary(
        net_monthly_income=income,
        total_savings=total_savings,
        savings_rate=savings_rate,
        total_expenses=total_expenses,
        required_expenses=required_expenses,
        discretionary_expenses=discretionary_expenses,
        emergency_expense_baseline=emergency_expense_baseline,
        buffer=cash_flow.buffer,
        expense_breakdown_by_category=expense_breakdown_by_category,
    )
