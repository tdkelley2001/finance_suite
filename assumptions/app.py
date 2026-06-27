import pandas as pd
import streamlit as st

from suite.state import (
    DEFAULT_GLOBAL_ASSUMPTIONS,
    get_user_state,
    update_assumption,
)
from suite.tools import SuiteTool
from suite.ui import render_tool_header, safe_float


ASSUMPTION_LABELS = {
    "inflation": "Inflation",
    "expected_portfolio_return": "Expected Portfolio Return",
    "expected_portfolio_volatility": "Expected Portfolio Volatility",
    "cash_return": "Cash Return",
    "mortgage_rate": "Mortgage Rate",
    "property_tax_rate": "Property Tax Rate",
    "homeowners_insurance_annual": "Annual Homeowners Insurance",
    "pmi_rate": "PMI Rate",
    "home_appreciation": "Home Appreciation",
    "rent_growth": "Rent Growth",
    "default_tax_rate": "Default Tax Rate",
    "capital_gains_tax_rate": "Capital Gains Tax Rate",
    "default_withdrawal_rate": "Default Withdrawal Rate",
    "planning_horizon_years": "Planning Horizon (Years)",
    "recommended_emergency_months": "Recommended Emergency Fund (Months)",
}

PERCENT_KEYS = {
    "inflation",
    "expected_portfolio_return",
    "expected_portfolio_volatility",
    "cash_return",
    "mortgage_rate",
    "property_tax_rate",
    "pmi_rate",
    "home_appreciation",
    "rent_growth",
    "default_tax_rate",
    "capital_gains_tax_rate",
    "default_withdrawal_rate",
}


def render_assumptions_manager(tool: SuiteTool) -> None:
    render_tool_header(tool)

    state = get_user_state()
    assumptions_df = _assumptions_to_dataframe(state.assumptions.global_defaults)

    edited = st.data_editor(
        assumptions_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Key": st.column_config.TextColumn(disabled=True),
            "Assumption": st.column_config.TextColumn(disabled=True),
            "Display Value": st.column_config.TextColumn(disabled=True),
            "Value": st.column_config.NumberColumn(format="%.4f"),
        },
        key="assumptions_manager_editor",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        apply_changes = st.button("Apply", type="primary")
    with col2:
        reset_defaults = st.button("Reset to defaults")

    if reset_defaults:
        for key, value in DEFAULT_GLOBAL_ASSUMPTIONS.items():
            update_assumption(
                key,
                value,
                source_id="assumptions_manager",
                label=ASSUMPTION_LABELS.get(key, key),
            )
        st.success("Assumptions reset to defaults.")

    if apply_changes:
        for _, row in edited.iterrows():
            key = str(row["Key"])
            update_assumption(
                key,
                _coerce_assumption_value(key, row["Value"]),
                source_id="assumptions_manager",
                label=str(row["Assumption"]),
            )
        st.success("Assumptions updated.")

    st.subheader("Current Defaults")
    st.dataframe(
        _assumptions_to_dataframe(get_user_state().assumptions.global_defaults)[
            ["Assumption", "Display Value"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def _assumptions_to_dataframe(values: dict) -> pd.DataFrame:
    rows = []
    keys = list(DEFAULT_GLOBAL_ASSUMPTIONS.keys())
    for key in values:
        if key not in keys:
            keys.append(key)

    for key in keys:
        value = values.get(key, DEFAULT_GLOBAL_ASSUMPTIONS.get(key, 0.0))
        rows.append(
            {
                "Key": key,
                "Assumption": ASSUMPTION_LABELS.get(
                    key, key.replace("_", " ").title()
                ),
                "Value": value,
                "Display Value": _format_assumption_value(key, value),
            }
        )
    return pd.DataFrame(rows)


def _format_assumption_value(key: str, value) -> str:
    numeric = safe_float(value)
    if key in PERCENT_KEYS:
        return f"{numeric * 100:.2f}%"
    if key.endswith("_years"):
        return f"{numeric:.0f} years"
    if key.endswith("_months"):
        return f"{numeric:.0f} months"
    return f"{numeric:.4f}"


def _coerce_assumption_value(key: str, value):
    numeric = safe_float(value)
    if key.endswith("_years"):
        return int(round(numeric))
    if key.endswith("_months"):
        return int(round(numeric))
    return numeric
