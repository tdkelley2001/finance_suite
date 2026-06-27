from .models import (
    MortgageAssumptions,
    Household,
    CashPosition,
    AffordabilityConstraints,
    MonthlyHousingCost,
    AffordabilityResult,
)
from suite.calculations import (
    cash_required,
    constrained_payment_limit,
    fixed_payment,
)


def monthly_mortgage_payment(
    loan_amount: float,
    annual_rate: float,
    term_years: int,
) -> float:
    return fixed_payment(loan_amount, annual_rate, term_years)


def housing_cost_from_price(
    home_price: float,
    mortgage: MortgageAssumptions,
    cash: CashPosition,
) -> MonthlyHousingCost:
    down_payment = home_price * cash.down_payment_pct
    loan_amount = home_price - down_payment

    pi = monthly_mortgage_payment(
        loan_amount,
        mortgage.interest_rate,
        mortgage.term_years,
    )

    tax = home_price * mortgage.property_tax_rate / 12
    insurance = mortgage.annual_insurance / 12
    hoa = mortgage.monthly_hoa

    pmi = 0.0
    if cash.down_payment_pct < 0.20:
        pmi = loan_amount * mortgage.pmi_rate / 12

    return MonthlyHousingCost(
        principal_and_interest=pi,
        property_tax=tax,
        insurance=insurance,
        hoa=hoa,
        pmi=pmi,
    )


def max_payment_from_constraints(
    household: Household,
    constraints: AffordabilityConstraints,
) -> float:
    return constrained_payment_limit(
        income=household.net_monthly_income,
        payment_ratio=constraints.max_payment_ratio,
        non_payment_expenses=household.non_housing_expenses,
        planned_savings=household.planned_savings,
        minimum_buffer=household.min_monthly_buffer,
    )


def cash_required_for_price(
    home_price: float,
    cash: CashPosition,
) -> float:
    return cash_required(
        amount=home_price,
        upfront_pct=cash.down_payment_pct,
        transaction_cost_pct=cash.closing_cost_pct,
        reserves=cash.reserve_requirement,
    )


def solve_max_affordable_price(
    mortgage: MortgageAssumptions,
    household: Household,
    cash: CashPosition,
    constraints: AffordabilityConstraints,
    price_floor: float = 50_000,
    price_ceiling: float = 2_000_000,
    step: float = 1_000,
) -> AffordabilityResult:
    max_payment = max_payment_from_constraints(household, constraints)

    binding = "unknown"
    best_price = 0.0
    best_cost = None

    price = price_floor
    while price <= price_ceiling:
        monthly_cost = housing_cost_from_price(price, mortgage, cash)

        if monthly_cost.total > max_payment:
            binding = "monthly_payment"
            break

        if cash_required_for_price(price, cash) > cash.cash_available:
            binding = "cash"
            break

        best_price = price
        best_cost = monthly_cost
        price += step

    if best_cost is None:
        best_cost = housing_cost_from_price(0.0, mortgage, cash)
        binding = "insufficient_capacity"

    return AffordabilityResult(
        max_home_price=best_price,
        max_monthly_payment=max_payment,
        monthly_cost=best_cost,
        binding_constraint=binding,
    )
