import streamlit as st
from housing_affordability.engine import (
    housing_cost_from_price,
    solve_max_affordable_price,
    cash_required_for_price,
    max_payment_from_constraints,
)
from housing_affordability.models import AffordabilityResult
from housing_affordability.ui_inputs import (
    render_mode_selector,
    render_sidebar_inputs,
    render_mode_inputs,
)
from housing_affordability.ui_outputs import (
    render_summary,
    render_details,
)


def render_housing_affordability():
    st.header("🏠 Housing Affordability")

    mode = render_mode_selector()
    household, cash, mortgage, constraints = render_sidebar_inputs()
    mode_inputs = render_mode_inputs(mode)

    max_feasible_payment = max_payment_from_constraints(
        household, constraints
    )

    if mode == "Evaluate a specific home":
        home_price = mode_inputs["home_price"]
        preferred = mode_inputs["preferred_housing_cost"]

        monthly_cost = housing_cost_from_price(
            home_price, mortgage, cash
        )

        total_cash_required = cash_required_for_price(
            home_price, cash
        )

        buffer_remaining = (
            household.net_monthly_income
            - household.non_housing_expenses
            - household.planned_savings
            - monthly_cost.total
        )

        # ---- feasibility ----
        if total_cash_required > cash.cash_available:
            binding = "cash"
            status = "Not Affordable"
        elif (
            monthly_cost.total > max_feasible_payment
            or buffer_remaining < household.min_monthly_buffer
        ):
            binding = "monthly_payment"
            status = "Not Affordable"
        else:
            binding = "none"
            if preferred > 0 and monthly_cost.total > preferred:
                status = "Stretch"
            else:
                status = "Comfortable"

        result = AffordabilityResult(
            max_home_price=home_price,
            max_monthly_payment=max_feasible_payment,
            monthly_cost=monthly_cost,
            binding_constraint=binding,
        )

    else:
        result = solve_max_affordable_price(
            mortgage=mortgage,
            household=household,
            cash=cash,
            constraints=constraints,
        )

        total_cash_required = cash_required_for_price(
            result.max_home_price, cash
        )

        status = "Maximum Feasible"

    cash_breakdown = [
        result.max_home_price * cash.down_payment_pct,
        result.max_home_price * cash.closing_cost_pct,
        cash.reserve_requirement,
        total_cash_required,
    ]

    assumptions_dict = {
        "household": household.__dict__,
        "cash": cash.__dict__,
        "mortgage": mortgage.__dict__,
        "constraints": constraints.__dict__,
        "mode": mode,
    }

    render_summary(
        result,
        total_cash_required,
        status=status,
    )

    render_details(
        result.monthly_cost,
        cash_breakdown,
        assumptions_dict,
    )