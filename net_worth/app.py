import pandas as pd
import streamlit as st

from net_worth.engine import (
    calculate_balance_sheet,
    tax_treatment_for_account_type,
)
from suite.state import (
    Asset,
    FinancialAccount,
    Liability,
    dataframe_to_records,
    get_user_state,
    update_net_worth_profile,
    update_tool_output,
    update_tool_state,
)
from suite.tools import SuiteTool
from suite.ui import money, render_tool_header, safe_float


ACCOUNT_TYPES = [
    "Cash",
    "Checking",
    "Savings",
    "Money Market",
    "Taxable Brokerage",
    "401(k)",
    "Roth 401(k)",
    "403(b)",
    "Roth 403(b)",
    "457(b)",
    "Roth 457(b)",
    "IRA",
    "Roth IRA",
    "HSA",
    "529",
    "Other",
]

TAX_TREATMENTS = [
    "Cash",
    "Taxable",
    "Pre-tax",
    "Roth",
    "HSA",
    "529",
    "Other",
]

ASSET_TYPES = [
    "Home",
    "Vehicle",
    "Business",
    "Personal Property",
    "Other",
]

LIABILITY_TYPES = [
    "Mortgage",
    "Credit Card",
    "Student Loan",
    "Auto Loan",
    "Personal Loan",
    "Other",
]


def render_net_worth(tool: SuiteTool) -> None:
    render_tool_header(tool)

    profile = get_user_state().profile
    accounts_df = _session_dataframe(
        "net_worth_accounts_df",
        _accounts_to_dataframe(profile.accounts),
    )
    assets_df = _session_dataframe(
        "net_worth_assets_df",
        _assets_to_dataframe(profile.assets),
    )
    liabilities_df = _session_dataframe(
        "net_worth_liabilities_df",
        _liabilities_to_dataframe(profile.liabilities),
    )

    tab_accounts, tab_assets, tab_liabilities = st.tabs(
        ["Accounts", "Other Assets", "Liabilities"]
    )

    with tab_accounts:
        with st.form("net_worth_accounts_form"):
            edited_accounts = st.data_editor(
                accounts_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Account Type": st.column_config.SelectboxColumn(
                        options=ACCOUNT_TYPES
                    ),
                    "Tax Treatment": st.column_config.SelectboxColumn(
                        options=TAX_TREATMENTS,
                        help="Defaults from account type; edit if your account is different.",
                    ),
                    "Balance": st.column_config.NumberColumn(format="$%.2f"),
                },
                key="net_worth_accounts_editor",
            )
            apply_accounts = st.form_submit_button(
                "Apply accounts",
                use_container_width=True,
            )
        if apply_accounts:
            st.session_state["net_worth_accounts_df"] = edited_accounts
            st.success("Accounts applied.")

    with tab_assets:
        with st.form("net_worth_assets_form"):
            edited_assets = st.data_editor(
                assets_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Asset Type": st.column_config.SelectboxColumn(
                        options=ASSET_TYPES
                    ),
                    "Value": st.column_config.NumberColumn(format="$%.2f"),
                },
                key="net_worth_assets_editor",
            )
            apply_assets = st.form_submit_button(
                "Apply assets",
                use_container_width=True,
            )
        if apply_assets:
            st.session_state["net_worth_assets_df"] = edited_assets
            st.success("Assets applied.")

    with tab_liabilities:
        with st.form("net_worth_liabilities_form"):
            edited_liabilities = st.data_editor(
                liabilities_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Liability Type": st.column_config.SelectboxColumn(
                        options=LIABILITY_TYPES
                    ),
                    "Balance": st.column_config.NumberColumn(format="$%.2f"),
                    "Monthly Payment": st.column_config.NumberColumn(format="$%.2f"),
                    "Interest Rate": st.column_config.NumberColumn(format="%.2f%%"),
                },
                key="net_worth_liabilities_editor",
            )
            apply_liabilities = st.form_submit_button(
                "Apply liabilities",
                use_container_width=True,
            )
        if apply_liabilities:
            st.session_state["net_worth_liabilities_df"] = edited_liabilities
            st.success("Liabilities applied.")

    applied_accounts_df = st.session_state["net_worth_accounts_df"]
    applied_assets_df = st.session_state["net_worth_assets_df"]
    applied_liabilities_df = st.session_state["net_worth_liabilities_df"]

    accounts = _accounts_from_dataframe(applied_accounts_df)
    assets = _assets_from_dataframe(applied_assets_df)
    liabilities = _liabilities_from_dataframe(applied_liabilities_df)
    balance_sheet = calculate_balance_sheet(accounts, assets, liabilities)

    if apply_accounts or apply_assets or apply_liabilities:
        update_net_worth_profile(
            accounts=accounts,
            assets=assets,
            liabilities=liabilities,
            balance_sheet=balance_sheet,
        )
        update_tool_state(
            "net_worth",
            {
                "accounts": dataframe_to_records(applied_accounts_df),
                "assets": dataframe_to_records(applied_assets_df),
                "liabilities": dataframe_to_records(applied_liabilities_df),
            },
        )
        update_tool_output(
            "net_worth",
            {
                "total_assets": balance_sheet.total_assets,
                "total_liabilities": balance_sheet.total_liabilities,
                "net_worth": balance_sheet.net_worth,
                "liquid_assets": balance_sheet.liquid_assets,
                "retirement_assets": balance_sheet.retirement_assets,
                "taxable_assets": balance_sheet.taxable_assets,
            },
        )

    st.subheader("Net Worth Snapshot")
    c1, c2, c3 = st.columns(3)
    c1.metric("Assets", money(balance_sheet.total_assets))
    c2.metric("Liabilities", money(balance_sheet.total_liabilities))
    c3.metric("Net Worth", money(balance_sheet.net_worth))

    c4, c5, c6 = st.columns(3)
    c4.metric("Liquid Assets", money(balance_sheet.liquid_assets))
    c5.metric("Retirement Assets", money(balance_sheet.retirement_assets))
    c6.metric("Taxable Assets", money(balance_sheet.taxable_assets))


def _session_dataframe(key: str, default: pd.DataFrame) -> pd.DataFrame:
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def _accounts_to_dataframe(accounts: list[FinancialAccount]) -> pd.DataFrame:
    rows = [
        {
            "Name": account.name,
            "Account Type": account.account_type,
            "Tax Treatment": account.tax_treatment
            or tax_treatment_for_account_type(account.account_type),
            "Balance": account.balance,
        }
        for account in accounts
    ]
    if not rows:
        rows = [
            {
                "Name": "Checking",
                "Account Type": "Checking",
                "Tax Treatment": tax_treatment_for_account_type("Checking"),
                "Balance": 0.0,
            },
            {
                "Name": "Retirement",
                "Account Type": "401(k)",
                "Tax Treatment": tax_treatment_for_account_type("401(k)"),
                "Balance": 0.0,
            },
        ]
    return pd.DataFrame(rows)


def _assets_to_dataframe(assets: list[Asset]) -> pd.DataFrame:
    rows = [
        {
            "Name": asset.name,
            "Asset Type": asset.asset_type,
            "Value": asset.value,
        }
        for asset in assets
    ]
    if not rows:
        rows = [{"Name": "Home", "Asset Type": "Home", "Value": 0.0}]
    return pd.DataFrame(rows)


def _liabilities_to_dataframe(liabilities: list[Liability]) -> pd.DataFrame:
    rows = [
        {
            "Name": liability.name,
            "Liability Type": liability.liability_type,
            "Balance": liability.balance,
            "Monthly Payment": liability.payment,
            "Interest Rate": liability.interest_rate * 100,
        }
        for liability in liabilities
    ]
    if not rows:
        rows = [
            {
                "Name": "Mortgage",
                "Liability Type": "Mortgage",
                "Balance": 0.0,
                "Monthly Payment": 0.0,
                "Interest Rate": 0.0,
            }
        ]
    return pd.DataFrame(rows)


def _accounts_from_dataframe(df: pd.DataFrame) -> list[FinancialAccount]:
    accounts = []
    for _, row in df.iterrows():
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        account_type = str(row.get("Account Type") or "Other")
        tax_treatment = str(row.get("Tax Treatment") or "").strip()
        accounts.append(
            FinancialAccount(
                name=name,
                account_type=account_type,
                tax_treatment=tax_treatment or tax_treatment_for_account_type(account_type),
                balance=safe_float(row.get("Balance")),
            )
        )
    return accounts


def _assets_from_dataframe(df: pd.DataFrame) -> list[Asset]:
    assets = []
    for _, row in df.iterrows():
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        assets.append(
            Asset(
                name=name,
                asset_type=str(row.get("Asset Type") or "Other"),
                value=safe_float(row.get("Value")),
            )
        )
    return assets


def _liabilities_from_dataframe(df: pd.DataFrame) -> list[Liability]:
    liabilities = []
    for _, row in df.iterrows():
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        liabilities.append(
            Liability(
                name=name,
                liability_type=str(row.get("Liability Type") or "Other"),
                balance=safe_float(row.get("Balance")),
                payment=safe_float(row.get("Monthly Payment")),
                interest_rate=safe_float(row.get("Interest Rate")) / 100,
            )
        )
    return liabilities
