from dataclasses import dataclass
from typing import Dict
from .models import BudgetProfile


@dataclass
class BudgetSummary:
    net_monthly_income: float
    total_savings: float
    total_expenses: float
    required_expenses: float
    discretionary_expenses: float
    buffer: float
    expense_breakdown_by_category: Dict[str, float]


def calculate_budget_summary(profile: BudgetProfile) -> BudgetSummary:
    income = profile.assumptions.net_monthly_income

    total_savings = sum(
        s.monthly_amount for s in profile.assumptions.savings
    )

    total_expenses = sum(
        e.monthly_amount for e in profile.expenses
    )

    required_expenses = sum(
        e.monthly_amount for e in profile.expenses if e.required
    )

    discretionary_expenses = total_expenses - required_expenses

    buffer = income - total_savings - total_expenses

    expense_breakdown_by_category: Dict[str, float] = {}
    for e in profile.expenses:
        expense_breakdown_by_category.setdefault(e.category, 0.0)
        expense_breakdown_by_category[e.category] += e.monthly_amount

    return BudgetSummary(
        net_monthly_income=income,
        total_savings=total_savings,
        total_expenses=total_expenses,
        required_expenses=required_expenses,
        discretionary_expenses=discretionary_expenses,
        buffer=buffer,
        expense_breakdown_by_category=expense_breakdown_by_category,
    )