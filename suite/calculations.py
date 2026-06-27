from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CashFlowSnapshot:
    income: float
    required_expenses: float
    discretionary_expenses: float
    savings: float = 0.0

    @property
    def total_expenses(self) -> float:
        return self.required_expenses + self.discretionary_expenses

    @property
    def buffer(self) -> float:
        return self.income - self.savings - self.total_expenses


def fixed_payment(
    principal: float,
    annual_rate: float,
    term_years: int,
    payments_per_year: int = 12,
) -> float:
    if principal <= 0:
        return 0.0
    if term_years <= 0:
        raise ValueError("term_years must be positive")
    if payments_per_year <= 0:
        raise ValueError("payments_per_year must be positive")

    n_payments = term_years * payments_per_year
    periodic_rate = annual_rate / payments_per_year

    if periodic_rate == 0:
        return principal / n_payments

    return (
        principal
        * periodic_rate
        / (1 - (1 + periodic_rate) ** -n_payments)
    )


def amortization_schedule(
    principal: float,
    annual_rate: float,
    term_years: int,
    horizon_years: int,
    payments_per_year: int = 12,
) -> pd.DataFrame:
    if horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    payment = fixed_payment(
        principal,
        annual_rate,
        term_years,
        payments_per_year=payments_per_year,
    )
    periodic_rate = annual_rate / payments_per_year
    balance = principal
    rows = []

    for year in range(1, horizon_years + 1):
        interest_paid = 0.0
        principal_paid = 0.0

        for _ in range(payments_per_year):
            if balance <= 0:
                balance = 0.0
                break

            interest = balance * periodic_rate
            principal_component = min(payment - interest, balance)
            balance -= principal_component
            interest_paid += interest
            principal_paid += principal_component

        rows.append(
            {
                "year": year,
                "balance": balance,
                "principal_paid": principal_paid,
                "interest_paid": interest_paid,
            }
        )

    return pd.DataFrame(rows)


def cash_required(
    amount: float,
    upfront_pct: float,
    transaction_cost_pct: float = 0.0,
    reserves: float = 0.0,
) -> float:
    return amount * upfront_pct + amount * transaction_cost_pct + reserves


def cash_flow_snapshot(
    *,
    income: float,
    required_expenses: float = 0.0,
    discretionary_expenses: float = 0.0,
    savings: float = 0.0,
) -> CashFlowSnapshot:
    return CashFlowSnapshot(
        income=income,
        required_expenses=required_expenses,
        discretionary_expenses=discretionary_expenses,
        savings=savings,
    )


def constrained_payment_limit(
    *,
    income: float,
    payment_ratio: float,
    non_payment_expenses: float = 0.0,
    planned_savings: float = 0.0,
    minimum_buffer: float = 0.0,
) -> float:
    ratio_limit = income * payment_ratio
    buffer_limit = (
        income
        - non_payment_expenses
        - planned_savings
        - minimum_buffer
    )
    return min(ratio_limit, buffer_limit)


def compound_value(principal: float, returns: Iterable[float]) -> float:
    value = principal
    for rate in returns:
        value *= 1 + float(rate)
    return value

