import streamlit as st
from housing_affordability.app import render_housing_affordability
from rent_vs_buy.app import render_rent_vs_buy
from budget.app import render_budget

st.set_page_config(
        page_title="Money Lab",
        layout="wide",
    )
st.title("Money Lab")
st.caption("Transparent financial models for exploring tradeoffs, risk, and assumptions.")

tool = st.sidebar.selectbox(
    "Select a tool",
    [
        "🏠 Housing Affordability",
        "📊 Rent vs Buy",
        "💰 Budget & Cash Flow",
    ],
)

if tool == "🏠 Housing Affordability":
    render_housing_affordability()
elif tool == "📊 Rent vs Buy":
    render_rent_vs_buy()
elif tool == "💰 Budget & Cash Flow":
    render_budget()