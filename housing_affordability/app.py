from dataclasses import asdict

from housing_affordability.engine import (
    housing_cost_from_price,
    solve_max_affordable_price,
    cash_required_for_price,
    max_payment_from_constraints,
)
from housing_affordability.models import AffordabilityResult
import streamlit as st

from suite.state import (
    SharedCashFlowState,
    update_cash_flow,
    update_tool_output,
    update_tool_state,
)
from suite.tools import SuiteTool
from suite.ui import render_tool_header
from housing_affordability.ui_inputs import (
    render_mode_selector,
    render_sidebar_inputs,
    render_mode_inputs,
)
from housing_affordability.ui_outputs import (
    render_summary,
    render_details,
)


def render_housing_affordability(tool: SuiteTool) -> None:
    render_tool_header(tool)

    mode = render_mode_selector()
    household, cash, mortgage, constraints = render_sidebar_inputs()
    update_cash_flow(
        SharedCashFlowState(
            net_monthly_income=household.net_monthly_income,
            required_monthly_expenses=household.non_housing_expenses,
            discretionary_monthly_expenses=0.0,
            planned_monthly_savings=household.planned_savings,
            min_monthly_buffer=household.min_monthly_buffer,
            source="housing_affordability",
        )
    )
    mode_inputs = render_mode_inputs(mode)
    update_tool_state(
        "housing_affordability",
        {
            "mode": st.session_state.get("housing_mode"),
            "cash_available": st.session_state.get("housing_cash_available"),
            "down_payment_pct": st.session_state.get("housing_down_payment_pct"),
            "closing_cost_pct": st.session_state.get("housing_closing_cost_pct"),
            "reserve_requirement": st.session_state.get("housing_reserve_requirement"),
            "interest_rate": st.session_state.get("housing_interest_rate"),
            "term_years": st.session_state.get("housing_term_years"),
            "property_tax_rate": st.session_state.get("housing_property_tax_rate"),
            "annual_insurance": st.session_state.get("housing_annual_insurance"),
            "monthly_hoa": st.session_state.get("housing_monthly_hoa"),
            "pmi_rate": st.session_state.get("housing_pmi_rate"),
            "max_payment_ratio": st.session_state.get("housing_max_payment_ratio"),
            "home_price": st.session_state.get("housing_home_price"),
            "preferred_housing_cost": st.session_state.get("housing_preferred_housing_cost"),
        },
    )

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
        "household": asdict(household),
        "cash": asdict(cash),
        "mortgage": asdict(mortgage),
        "constraints": asdict(constraints),
        "mode": mode,
    }

    render_summary(
        result,
        total_cash_required,
        status=status,
    )
    update_tool_output(
        "housing_affordability",
        {
            "status": status,
            "max_home_price": result.max_home_price,
            "max_monthly_payment": result.max_monthly_payment,
            "monthly_housing_cost": result.monthly_cost.total,
            "cash_required": total_cash_required,
            "binding_constraint": result.binding_constraint,
        },
    )

    render_details(
        result.monthly_cost,
        cash_breakdown,
        assumptions_dict,
    )
