import streamlit as st
import pandas as pd

from budget.defaults import get_default_expenses_df
from budget.engine import calculate_budget_summary
from budget.models import (
    BudgetProfile,
    BudgetAssumptions,
    BudgetExpense,
    SavingsItem,
)
from budget.io import budget_to_dataframe
from suite.tools import SuiteTool
from suite.state import (
    SharedCashFlowState,
    dataframe_to_records,
    get_user_state,
    update_cash_flow,
    update_tool_output,
    update_tool_state,
)
from suite.ui import money, read_package_text, render_tool_header, safe_float


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
def render_budget(tool: SuiteTool) -> None:
    # ----------------------------------
    # Page header
    # ----------------------------------
    render_tool_header(tool)
    shared_cash_flow = get_user_state().cash_flow

    st.download_button(
        "Download blank budget template",
        read_package_text("budget", "templates/budget_template.csv"),
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
            value=shared_cash_flow.net_monthly_income,
            step=100.0,
            key="budget_net_monthly_income",
        )

    with col2:
        planned_savings = st.number_input(
            "Planned monthly savings",
            min_value=0.0,
            value=shared_cash_flow.planned_monthly_savings,
            step=100.0,
            help="Retirement contributions, brokerage transfers, etc.",
            key="budget_planned_savings",
        )

    st.divider()

    # ----------------------------------
    # Expenses editor (session-backed)
    # ----------------------------------
    st.caption(
        "This starter list includes common expense categories. "
        "Fill in what applies to you, leave blank or remove rows you do not need, and add any additional rows you need."
    )
    if "expenses_df" not in st.session_state:
        st.session_state.expenses_df = get_default_expenses_df()

    st.subheader("Monthly Expenses")

    with st.form("budget_expenses_form"):
        edited_expenses_df = st.data_editor(
            st.session_state.expenses_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Monthly Amount": st.column_config.NumberColumn(format="$%.2f"),
                "Required": st.column_config.CheckboxColumn(),
            },
            key="budget_expenses_editor",
        )
        apply_expenses = st.form_submit_button(
            "Apply expenses",
            use_container_width=True,
        )

    if apply_expenses:
        st.session_state.expenses_df = edited_expenses_df
        st.success("Expenses applied.")

    expenses_df = st.session_state.expenses_df

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
    update_cash_flow(
        SharedCashFlowState(
            net_monthly_income=summary.net_monthly_income,
            required_monthly_expenses=summary.required_expenses,
            discretionary_monthly_expenses=summary.discretionary_expenses,
            planned_monthly_savings=summary.total_savings,
            savings_rate=summary.savings_rate,
            emergency_expense_baseline=summary.emergency_expense_baseline,
            min_monthly_buffer=shared_cash_flow.min_monthly_buffer,
            source="budget",
        )
    )
    update_tool_state(
        "budget",
        {"expenses": dataframe_to_records(expenses_df)},
    )
    update_tool_output(
        "budget",
        {
            "net_monthly_income": summary.net_monthly_income,
            "total_savings": summary.total_savings,
            "savings_rate": summary.savings_rate,
            "total_expenses": summary.total_expenses,
            "required_expenses": summary.required_expenses,
            "discretionary_expenses": summary.discretionary_expenses,
            "emergency_expense_baseline": summary.emergency_expense_baseline,
            "buffer": summary.buffer,
        },
    )

    # -----------------------------
    # Outputs
    # -----------------------------
    st.subheader("Monthly Snapshot")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total expenses", money(summary.total_expenses))
    c2.metric("Required", money(summary.required_expenses))
    c3.metric("Discretionary", money(summary.discretionary_expenses))
    c4.metric("Remaining buffer", money(summary.buffer))

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
