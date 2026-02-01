import streamlit as st
import pandas as pd
import math

from budget.defaults import get_default_expenses_df
from budget.engine import calculate_budget_summary
from budget.models import (
    BudgetProfile,
    BudgetAssumptions,
    BudgetExpense,
    SavingsItem,
)
from budget.io import budget_to_dataframe


# ======================================================
# Helpers
# ======================================================
def safe_float(val) -> float:
    if val is None:
        return 0.0
    try:
        if isinstance(val, float) and math.isnan(val):
            return 0.0
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def build_budget_profile(
    *,
    net_monthly_income: float,
    planned_savings: float,
    expenses_df: pd.DataFrame,
) -> BudgetProfile:
    return BudgetProfile(
        assumptions=BudgetAssumptions(
            net_monthly_income=net_monthly_income,
            savings=[
                SavingsItem(
                    name="Planned savings",
                    monthly_amount=planned_savings,
                )
            ],
        ),
        expenses=[
            BudgetExpense(
                category=row["Category"],
                subcategory=row["Subcategory"],
                monthly_amount=safe_float(row["Monthly Amount"]),
                required=row["Required"],
            )
            for _, row in expenses_df.iterrows()
        ],
    )


# ======================================================
# Main UI
# ======================================================
def render_budget():
    # ----------------------------------
    # Page header
    # ----------------------------------
    st.header("💰 Monthly Budget")
    st.caption("A simple, editable view of your monthly cash flow")

    with open("budget/templates/budget_template.csv", "r") as f:
        st.download_button(
            "Download blank budget template",
            f.read(),
            file_name="budget_template.csv",
        )
    
    st.divider()

    # -----------------------------
    # Income & savings
    # -----------------------------
    col1, col2 = st.columns(2)

    with col1:
        net_monthly_income = st.number_input(
            "Net monthly income",
            min_value=0.0,
            value=0.0,
            step=100.0,
        )

    with col2:
        planned_savings = st.number_input(
            "Planned monthly savings",
            min_value=0.0,
            value=0.0,
            step=100.0,
            help="Retirement contributions, brokerage transfers, etc.",
        )

    st.divider()

    # ----------------------------------
    # Expenses editor (session-backed)
    # ----------------------------------
    st.caption(
        "This starter list includes common expense categories. "
        "Fill in what applies to you, leave blank or remove rows you don’t need, and add any additional rows you need."
    )
    if "expenses_df" not in st.session_state:
        st.session_state.expenses_df = get_default_expenses_df()

    st.subheader("Monthly Expenses")

    expenses_df = st.data_editor(
        st.session_state.expenses_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Monthly Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Required": st.column_config.CheckboxColumn(),
        },
    )

    st.session_state.expenses_df = expenses_df

    st.divider()

    # ----------------------------------
    # Build domain profile
    # ----------------------------------
    profile = build_budget_profile(
        net_monthly_income=net_monthly_income,
        planned_savings=planned_savings,
        expenses_df=expenses_df,
    )

    # ----------------------------------
    # Run engine
    # ----------------------------------
    summary = calculate_budget_summary(profile)

    # -----------------------------
    # Outputs
    # -----------------------------
    st.subheader("Monthly Snapshot")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total expenses", f"${summary.total_expenses:,.0f}")
    c2.metric("Required", f"${summary.required_expenses:,.0f}")
    c3.metric("Discretionary", f"${summary.discretionary_expenses:,.0f}")
    c4.metric("Remaining buffer", f"${summary.buffer:,.0f}")

    st.caption(
        "The remaining buffer represents income left after planned savings and expenses."
    )

    st.divider()

    # ----------------------------------
    # Exports
    # ----------------------------------
    csv = budget_to_dataframe(profile).to_csv(index=False)

    st.download_button(
        "Download budget (CSV)",
        csv,
        file_name="budget.csv",
        mime="text/csv",
    )
