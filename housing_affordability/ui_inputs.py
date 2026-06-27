import streamlit as st
from housing_affordability.models import (
    MortgageAssumptions,
    Household,
    CashPosition,
    AffordabilityConstraints,
)
from suite.state import get_assumption, get_user_state


def render_mode_selector() -> str:
    return st.radio(
        "How do you want to think about affordability?",
        [
            "Evaluate a specific home",
            "Find my maximum affordable home",
        ],
        horizontal=True,
        key="housing_mode",
        help=(
            "Evaluate a specific home price, or solve for the maximum home "
            "price your cash flow and savings can support."
        ),
    )


def render_sidebar_inputs():
    shared_cash_flow = get_user_state().cash_flow
    mortgage_rate = get_assumption("mortgage_rate", 0.065)
    property_tax_rate = get_assumption("property_tax_rate", 0.012)
    homeowners_insurance_annual = get_assumption(
        "homeowners_insurance_annual",
        1500.0,
    )
    pmi_rate = get_assumption("pmi_rate", 0.01)

    with st.sidebar:
        st.header("Cash Flow (Hard Constraints)")

        household = Household(
            net_monthly_income=st.number_input(
                "Net monthly income",
                min_value=0.0,
                value=shared_cash_flow.net_monthly_income or 6000.0,
                help="Monthly take-home income after taxes.",
                key="housing_net_monthly_income",
            ),
            non_housing_expenses=st.number_input(
                "Non-housing expenses",
                min_value=0.0,
                value=shared_cash_flow.non_housing_expenses or 3000.0,
                help="All recurring monthly expenses excluding housing.",
                key="housing_non_housing_expenses",
            ),
            planned_savings=st.number_input(
                "Planned savings",
                min_value=0.0,
                value=shared_cash_flow.planned_monthly_savings or 500.0,
                help="Monthly savings you plan to set aside.",
                key="housing_planned_savings",
            ),
            min_monthly_buffer=st.number_input(
                "Minimum remaining buffer",
                min_value=0.0,
                value=shared_cash_flow.min_monthly_buffer,
                help="Cash you want left over each month after all expenses.",
                key="housing_min_monthly_buffer",
            ),
        )

        st.header("Cash & Purchase")

        cash = CashPosition(
            cash_available=st.number_input(
                "Cash available",
                min_value=0.0,
                value=60000.0,
                help="Cash available for down payment, closing costs, and reserves.",
                key="housing_cash_available",
            ),
            down_payment_pct=st.slider(
                "Down payment (%)",
                3.0,
                30.0,
                20.0,
                key="housing_down_payment_pct",
            )
            / 100,
            closing_cost_pct=st.slider(
                "Closing costs (%)",
                0.0,
                5.0,
                3.0,
                key="housing_closing_cost_pct",
            )
            / 100,
            reserve_requirement=st.number_input(
                "Reserve requirement",
                min_value=0.0,
                value=10000.0,
                key="housing_reserve_requirement",
            ),
        )

        st.header("Mortgage")

        mortgage = MortgageAssumptions(
            interest_rate=st.number_input(
                "Interest rate (%)",
                min_value=0.0,
                value=float(mortgage_rate) * 100,
                key="housing_interest_rate",
            )
            / 100,
            term_years=st.selectbox(
                "Loan term",
                [15, 20, 30],
                index=2,
                key="housing_term_years",
            ),
            property_tax_rate=st.number_input(
                "Property tax rate (%)",
                min_value=0.0,
                value=float(property_tax_rate) * 100,
                key="housing_property_tax_rate",
            )
            / 100,
            annual_insurance=st.number_input(
                "Annual insurance",
                min_value=0.0,
                value=float(homeowners_insurance_annual),
                key="housing_annual_insurance",
            ),
            monthly_hoa=st.number_input(
                "Monthly HOA",
                min_value=0.0,
                value=0.0,
                key="housing_monthly_hoa",
            ),
            pmi_rate=st.number_input(
                "PMI rate (%)",
                min_value=0.0,
                value=float(pmi_rate) * 100,
                key="housing_pmi_rate",
            )
            / 100,
        )

        st.header("Constraints")

        constraints = AffordabilityConstraints(
            max_payment_ratio=st.slider(
                "Max housing payment (% of income)",
                20.0,
                45.0,
                30.0,
                key="housing_max_payment_ratio",
            )
            / 100
        )

    return household, cash, mortgage, constraints


def render_mode_inputs(mode: str):
    if mode == "Evaluate a specific home":
        return {
            "home_price": st.number_input(
                "Home price",
                min_value=0.0,
                value=400000.0,
                key="housing_home_price",
            ),
            "preferred_housing_cost": st.number_input(
                "Preferred monthly housing cost (optional)",
                min_value=0.0,
                value=0.0,
                help=(
                    "What you would like to pay for housing each month. "
                    "This does not affect feasibility, only how results are labeled."
                ),
                key="housing_preferred_housing_cost",
            ),
        }

    return {}
