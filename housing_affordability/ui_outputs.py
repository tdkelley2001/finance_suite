import streamlit as st
import pandas as pd


CONSTRAINT_EXPLANATIONS = {
    "monthly_payment": (
        "Monthly housing costs would exceed your income or buffer constraints."
    ),
    "cash": (
        "You do not have sufficient cash for the down payment, closing costs, "
        "and required reserves."
    ),
    "insufficient_capacity": (
        "Your current income and savings do not support homeownership "
        "under these assumptions."
    ),
    "none": "This home appears affordable under the selected constraints.",
    "unknown": "Constraint could not be determined.",
}


def render_summary(result, total_cash_required, status):
    st.subheader("Affordability Summary")

    c1, c2, c3 = st.columns(3)
    c1.metric("Home Price", f"${result.max_home_price:,.0f}")
    c2.metric("Monthly Housing Cost", f"${result.monthly_cost.total:,.0f}")
    c3.metric("Cash Required", f"${total_cash_required:,.0f}")

    c4, c5 = st.columns(2)
    c4.metric("Status", status)
    c5.metric(
        "Binding Constraint",
        result.binding_constraint.replace("_", " ").title(),
    )

    explanation = CONSTRAINT_EXPLANATIONS.get(
        result.binding_constraint, "No explanation available."
    )
    st.info(explanation)


def render_details(monthly_cost, cash_breakdown, assumptions_dict):
    tabs = st.tabs(
        ["Payment Breakdown", "Cash Required", "Sensitivity", "Assumptions"]
    )

    with tabs[0]:
        payment_df = pd.DataFrame(
            {
                "Component": [
                    "Principal & Interest",
                    "Property Tax",
                    "Insurance",
                    "HOA",
                    "PMI",
                ],
                "Monthly Cost": [
                    monthly_cost.principal_and_interest,
                    monthly_cost.property_tax,
                    monthly_cost.insurance,
                    monthly_cost.hoa,
                    monthly_cost.pmi,
                ],
            }
        )
        st.dataframe(payment_df, use_container_width=True)

    with tabs[1]:
        cash_df = pd.DataFrame(
            {
                "Item": [
                    "Down Payment",
                    "Closing Costs",
                    "Required Reserves",
                    "Total Cash Required",
                ],
                "Amount": cash_breakdown,
            }
        )
        st.dataframe(cash_df, use_container_width=True)

    with tabs[2]:
        st.caption(
            "Sensitivity analysis (interest rate and down payment) "
            "will be added in a future iteration."
        )

    with tabs[3]:
        rows = []
        for section, params in assumptions_dict.items():
            if isinstance(params, dict):
                for k, v in params.items():
                    rows.append(
                        {
                            "Category": section.title(),
                            "Parameter": k.replace("_", " ").title(),
                            "Value": v,
                        }
                    )
            else:
                rows.append(
                    {
                        "Category": "Mode",
                        "Parameter": section,
                        "Value": params,
                    }
                )

        assumptions_df = pd.DataFrame(rows)
        st.dataframe(assumptions_df, use_container_width=True)
