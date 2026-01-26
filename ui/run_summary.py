import streamlit as st
import pandas as pd

from ui.run_context import RunContext
from ui.assumptions_view import highlight_overrides


def render_model_summary(
        context: RunContext,
        rent_basis_label: str,
        override_count: int,
):
    st.subheader("Model Run Summary")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Scenario", context.scenario)
    c2.metric("Region", context.region)
    c3.metric("Horizon", f"{context.horizon} years")
    c4.metric("Overrides", override_count)

    c5, c6, c7, = st.columns(3)
    c5.metric("Rent Basis", rent_basis_label)
    c6.metric("Married", "Yes" if context.married else "No")
    c7.metric("Sell at End", "Yes" if context.sell_at_end else "No")


    st.caption(
        "Results below reflect the current scenario baseline plus any manual overrides. "
        "Use the assumptions summary to audit inputs."
    )

    st.divider()


def render_assumption_summary(
        override_count: int,
        assumption_rows: list[dict],
):
    st.subheader("Assumptions (Audit Trail)")

    with st.expander("Active Assumptions Summary", expanded=override_count > 0):
        assumptions_df = pd.DataFrame(assumption_rows)

        styled = (
            assumptions_df
            .style
            .apply(highlight_overrides, axis=1)
        )

        st.dataframe(styled, use_container_width=True)

        st.markdown("""
        Assumptions and Limitations:
        - Results depend heavily on assumptions and scenario selection.
        - Monte Carlo simulations represent hypothetical futures, not forecasts.
        - Taxes, financing constraints, and behavioral factors are simplified.
        - Liquidity risk and life events are not explicitly modeled.

        Use this tool to explore tradeoffs and sensitivity, not to make definitive decisions.
        """)