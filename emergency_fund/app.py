import streamlit as st

from emergency_fund.engine import (
    EmergencyFundInputs,
    calculate_emergency_fund,
    cash_balance_from_accounts,
)
from suite.state import (
    get_assumption,
    get_tool_state,
    get_user_state,
    update_tool_output,
    update_tool_state,
)
from suite.tools import SuiteTool
from suite.ui import money, render_tool_header


EXPENSE_BASIS_LABELS = {
    "Required expenses": "required",
    "Total expenses": "total",
}


def render_emergency_fund(tool: SuiteTool) -> None:
    render_tool_header(tool)

    state = get_user_state()
    cash_flow = state.profile.monthly_cash_flow
    balance_sheet = state.profile.balance_sheet
    saved_inputs = get_tool_state("emergency_fund")

    monthly_required_expenses = cash_flow.required_monthly_expenses
    monthly_total_expenses = cash_flow.non_housing_expenses
    monthly_net_income = cash_flow.net_monthly_income
    cash_balance = cash_balance_from_accounts(state.profile.accounts)
    liquid_assets = balance_sheet.liquid_assets

    if _missing_shared_inputs(
        monthly_required_expenses,
        monthly_total_expenses,
        monthly_net_income,
        cash_balance,
        liquid_assets,
    ):
        st.info(
            "This calculator reads Budget and Net Worth state. Add cash flow in "
            "Budget and account balances in Net Worth to make the results useful."
        )

    st.subheader("Shared Inputs")
    c1, c2, c3 = st.columns(3)
    c1.metric("Required expenses", money(monthly_required_expenses))
    c2.metric("Total expenses", money(monthly_total_expenses))
    c3.metric("Net income", money(monthly_net_income))

    c4, c5 = st.columns(2)
    c4.metric("Cash balance", money(cash_balance))
    c5.metric("Liquid assets", money(liquid_assets))

    st.divider()

    default_basis = saved_inputs.get("expense_basis", "required")
    default_label = _label_for_basis(default_basis)
    default_months = float(
        saved_inputs.get(
            "recommended_months",
            get_assumption("recommended_emergency_months", 6),
        )
    )
    default_months = min(max(int(round(default_months)), 1), 24)

    col1, col2 = st.columns(2)
    with col1:
        expense_basis_label = st.radio(
            "Target based on",
            list(EXPENSE_BASIS_LABELS),
            index=list(EXPENSE_BASIS_LABELS).index(default_label),
            horizontal=True,
        )
    with col2:
        recommended_months = st.slider(
            "Recommended months",
            min_value=1,
            max_value=24,
            value=default_months,
        )

    expense_basis = EXPENSE_BASIS_LABELS[expense_basis_label]
    inputs = EmergencyFundInputs(
        monthly_required_expenses=monthly_required_expenses,
        monthly_total_expenses=monthly_total_expenses,
        monthly_net_income=monthly_net_income,
        cash_balance=cash_balance,
        liquid_assets=liquid_assets,
        recommended_months=recommended_months,
        expense_basis=expense_basis,
    )
    result = calculate_emergency_fund(inputs)

    update_tool_state(
        "emergency_fund",
        {
            "expense_basis": expense_basis,
            "recommended_months": recommended_months,
        },
    )
    update_tool_output("emergency_fund", _summary(result, inputs))

    st.subheader("Emergency Fund Snapshot")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Target emergency fund", money(result.target_emergency_fund))
    r2.metric("Current coverage", f"{result.current_coverage_months:.1f} months")
    r3.metric("Gap / surplus", money(result.gap_surplus))
    r4.metric("Recommended", f"{result.recommended_months:.0f} months")

    st.caption(
        "Coverage and gap use cash balance. Liquid assets are shown separately "
        "because not all liquid assets are equally appropriate for emergency reserves."
    )

    st.subheader("Liquidity Context")
    l1, l2 = st.columns(2)
    l1.metric("Monthly expense basis", money(result.monthly_expense_basis))
    l2.metric(
        "Liquid asset coverage",
        f"{result.liquid_asset_coverage_months:.1f} months",
    )


def _missing_shared_inputs(*values: float) -> bool:
    return all(value <= 0 for value in values)


def _label_for_basis(expense_basis: str) -> str:
    for label, value in EXPENSE_BASIS_LABELS.items():
        if value == expense_basis:
            return label
    return "Required expenses"


def _summary(result, inputs: EmergencyFundInputs) -> dict:
    return {
        "target_emergency_fund": result.target_emergency_fund,
        "current_coverage_months": result.current_coverage_months,
        "gap_surplus": result.gap_surplus,
        "recommended_months": result.recommended_months,
        "monthly_expense_basis": result.monthly_expense_basis,
        "expense_basis": result.expense_basis,
        "monthly_required_expenses": inputs.monthly_required_expenses,
        "monthly_total_expenses": inputs.monthly_total_expenses,
        "monthly_net_income": inputs.monthly_net_income,
        "cash_balance": result.cash_balance,
        "liquid_assets": result.liquid_assets,
        "liquid_asset_coverage_months": result.liquid_asset_coverage_months,
    }
