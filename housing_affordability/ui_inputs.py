import streamlit as st
from housing_affordability.models import (
    MortgageAssumptions,
    Household,
    CashPosition,
    AffordabilityConstraints,
)


def render_mode_selector() -> str:
    return st.radio(
        "How do you want to think about affordability?",
        [
            "Evaluate a specific home",
            "Find my maximum affordable home",
        ],
        horizontal=True,
        help=(
            "Evaluate a specific home price, or solve for the maximum home "
            "price your cash flow and savings can support."
        ),
    )


def render_sidebar_inputs():
    with st.sidebar:
        st.header("Cash Flow (Hard Constraints)")

        household = Household(
            net_monthly_income=st.number_input(
                "Net monthly income",
                min_value=0.0,
                value=6000.0,
                help="Monthly take-home income after taxes.",
            ),
            non_housing_expenses=st.number_input(
                "Non-housing expenses",
                min_value=0.0,
                value=3000.0,
                help="All recurring monthly expenses excluding housing.",
            ),
            planned_savings=st.number_input(
                "Planned savings",
                min_value=0.0,
                value=500.0,
                help="Monthly savings you plan to set aside.",
            ),
            min_monthly_buffer=st.number_input(
                "Minimum remaining buffer",
                min_value=0.0,
                value=500.0,
                help="Cash you want left over each month after all expenses.",
            ),
        )

        st.header("Cash & Purchase")

        cash = CashPosition(
            cash_available=st.number_input(
                "Cash available",
                min_value=0.0,
                value=60000.0,
                help="Cash available for down payment, closing costs, and reserves.",
            ),
            down_payment_pct=st.slider(
                "Down payment (%)",
                3.0,
                30.0,
                20.0,
            )
            / 100,
            closing_cost_pct=st.slider(
                "Closing costs (%)",
                0.0,
                5.0,
                3.0,
            )
            / 100,
            reserve_requirement=st.number_input(
                "Reserve requirement",
                min_value=0.0,
                value=10000.0,
            ),
        )

        st.header("Mortgage")

        mortgage = MortgageAssumptions(
            interest_rate=st.number_input(
                "Interest rate (%)",
                min_value=0.0,
                value=6.5,
            )
            / 100,
            term_years=st.selectbox("Loan term", [15, 20, 30], index=2),
            property_tax_rate=st.number_input(
                "Property tax rate (%)",
                min_value=0.0,
                value=1.2,
            )
            / 100,
            annual_insurance=st.number_input(
                "Annual insurance",
                min_value=0.0,
                value=1500.0,
            ),
            monthly_hoa=st.number_input(
                "Monthly HOA",
                min_value=0.0,
                value=0.0,
            ),
            pmi_rate=st.number_input(
                "PMI rate (%)",
                min_value=0.0,
                value=1.0,
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
            ),
            "preferred_housing_cost": st.number_input(
                "Preferred monthly housing cost (optional)",
                min_value=0.0,
                value=0.0,
                help=(
                    "What you would like to pay for housing each month. "
                    "This does not affect feasibility, only how results are labeled."
                ),
            ),
        }

    return {}