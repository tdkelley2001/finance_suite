import streamlit as st
from rent_vs_buy.app import render_rent_vs_buy
from budget.app import render_budget

st.set_page_config(
        page_title="Money Lab",
        layout="wide",
    )
st.title("Financial Models Suite")

tool = st.sidebar.radio(
    "Choose a tool",
    ["Rent vs Buy", "Budget"],
)

if tool == "Rent vs Buy":
    render_rent_vs_buy()
elif tool == "Budget":
    render_budget()