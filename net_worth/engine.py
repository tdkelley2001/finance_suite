from __future__ import annotations

from dataclasses import dataclass

from suite.state import Asset, BalanceSheetState, FinancialAccount, Liability


LIQUID_ACCOUNT_TYPES = {
    "Cash",
    "Checking",
    "Savings",
    "Money Market",
    "Taxable Brokerage",
}

RETIREMENT_ACCOUNT_TYPES = {
    "401(k)",
    "Roth 401(k)",
    "403(b)",
    "Roth 403(b)",
    "457(b)",
    "Roth 457(b)",
    "IRA",
    "Roth IRA",
    "Retirement",
}

TAXABLE_ACCOUNT_TYPES = {
    "Taxable Brokerage",
    "Brokerage",
}

ACCOUNT_TAX_TREATMENTS = {
    "Cash": "Cash",
    "Checking": "Cash",
    "Savings": "Cash",
    "Money Market": "Cash",
    "Taxable Brokerage": "Taxable",
    "Brokerage": "Taxable",
    "401(k)": "Pre-tax",
    "403(b)": "Pre-tax",
    "457(b)": "Pre-tax",
    "IRA": "Pre-tax",
    "Roth 401(k)": "Roth",
    "Roth 403(b)": "Roth",
    "Roth 457(b)": "Roth",
    "Roth IRA": "Roth",
    "HSA": "HSA",
    "529": "529",
    "Other": "Other",
}


def tax_treatment_for_account_type(account_type: str) -> str:
    return ACCOUNT_TAX_TREATMENTS.get(account_type, "Other")


def effective_tax_treatment(account: FinancialAccount) -> str:
    return account.tax_treatment or tax_treatment_for_account_type(account.account_type)


@dataclass(frozen=True)
class NetWorthSummary:
    total_assets: float
    total_liabilities: float
    net_worth: float
    liquid_assets: float
    retirement_assets: float
    taxable_assets: float


def calculate_balance_sheet(
    accounts: list[FinancialAccount],
    assets: list[Asset],
    liabilities: list[Liability],
) -> BalanceSheetState:
    account_assets = sum(account.balance for account in accounts)
    standalone_assets = sum(asset.value for asset in assets)
    total_assets = account_assets + standalone_assets
    total_liabilities = sum(liability.balance for liability in liabilities)

    liquid_assets = sum(
        account.balance
        for account in accounts
        if effective_tax_treatment(account) in {"Cash", "Taxable"}
    )
    retirement_assets = sum(
        account.balance
        for account in accounts
        if effective_tax_treatment(account) in {"Pre-tax", "Roth"}
    )
    taxable_assets = sum(
        account.balance
        for account in accounts
        if effective_tax_treatment(account) == "Taxable"
    )

    return BalanceSheetState(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=total_assets - total_liabilities,
        liquid_assets=liquid_assets,
        retirement_assets=retirement_assets,
        taxable_assets=taxable_assets,
    )


def summarize_balance_sheet(balance_sheet: BalanceSheetState) -> NetWorthSummary:
    return NetWorthSummary(
        total_assets=balance_sheet.total_assets,
        total_liabilities=balance_sheet.total_liabilities,
        net_worth=balance_sheet.net_worth,
        liquid_assets=balance_sheet.liquid_assets,
        retirement_assets=balance_sheet.retirement_assets,
        taxable_assets=balance_sheet.taxable_assets,
    )
