import pandas as pd

from rent_vs_buy.engine.mortgage import mortgage_schedule
from rent_vs_buy.engine.rate_provider import DeterministicRateProvider, RateProvider
from rent_vs_buy.engine.assumptions import Assumptions


def build_yearly_df(assump: Assumptions, rate_provider: RateProvider = None) -> pd.DataFrame:
    if rate_provider is None:
        rate_provider = DeterministicRateProvider(assump)

    mortgage_df, annual_mortgage_payment, loan_amount = mortgage_schedule(assump)

    # Rent basis: market uses region monthly_rent, mortgage_matched uses the mortgage payment in year 1
    if assump.rent_basis == "match_mortgage":
        base_annual_rent = annual_mortgage_payment
    elif assump.rent_basis == "match_owner_cost":
        # Approximate owner costs in year 1
        maintenance = assump.home_price * assump.maintenance_pct
        property_tax = assump.home_price * assump.property_tax_pct
        hoa_annual = assump.hoa_monthly * 12
        home_insurance = assump.homeowners_insurance_annual
        owner_costs_year1 = (
            annual_mortgage_payment
            + property_tax
            + maintenance
            + hoa_annual
            + home_insurance
        )
        base_annual_rent = owner_costs_year1
    else:
        base_annual_rent = assump.monthly_rent * 12
    
    home_value = assump.home_price
    annual_rent = base_annual_rent
    inflation_index = 1.0

    renter_balance = assump.home_price * (assump.down_payment_pct + assump.closing_costs_pct)

    rows = []
    for year in range(1, assump.horizon + 1):
        inv_r = rate_provider.get("investment_return", year)
        home_r = rate_provider.get("home_appreciation", year)
        rent_g = rate_provider.get("rent_growth", year)
        infl = rate_provider.get("inflation", year)

        # ---- USE CURRENT VALUES (Year t) ----
        maintenance = home_value * assump.maintenance_pct
        property_tax = home_value * assump.property_tax_pct
        hoa_annual = (assump.hoa_monthly * 12) * inflation_index
        home_insurance = assump.homeowners_insurance_annual * inflation_index
        renters_insurance = assump.renters_insurance_annual * inflation_index

        principal_paid = float(mortgage_df.loc[year - 1, "principal_paid"])
        interest_paid = float(mortgage_df.loc[year - 1, "interest_paid"])
        mortgage_balance = float(mortgage_df.loc[year - 1, "mortgage_balance"])

        ltv = mortgage_balance / home_value if home_value > 0 else float("inf")

        # PMI: constant nominal amount while LTV above cutoff, only if DP < 20%
        pmi_paid = 0.0
        if assump.down_payment_pct < 0.20 and ltv > assump.pmi_ltv_cutoff:
            pmi_paid = assump.pmi_rate * loan_amount

        owner_cash_outflow = (
            principal_paid
            + interest_paid
            + pmi_paid
            + property_tax
            + maintenance
            + hoa_annual
            + home_insurance
        )

        renter_cash_outflow = annual_rent + renters_insurance
        renter_surplus = owner_cash_outflow - renter_cash_outflow

        # Investment growth for renter
        inv_after_tax = inv_r * (1 - assump.investment_tax_drag)
        renter_balance *= (1 + inv_after_tax)
        renter_balance += renter_surplus

        equity = home_value - mortgage_balance

        inflation_index *= (1 + infl)
        home_value *= (1 + home_r)

        rows.append(
            {
                "year": year,
                "home_value": home_value,
                "mortgage_balance": mortgage_balance,
                "principal_paid": principal_paid,
                "interest_paid": interest_paid,
                "pmi_paid": pmi_paid,
                "ltv": ltv,
                "property_tax": property_tax,
                "maintenance": maintenance,
                "hoa_annual": hoa_annual,
                "home_insurance": home_insurance,
                "annual_rent": annual_rent,
                "renters_insurance": renters_insurance,
                "owner_cash_outflow": owner_cash_outflow,
                "renter_cash_outflow": renter_cash_outflow,
                "renter_surplus": renter_surplus,
                "renter_balance": renter_balance,
                "owner_net_worth": equity,
                "renter_net_worth": renter_balance,
                "inflation_rate": infl,
                "investment_return": inv_r,
                "investment_return_after_tax": inv_after_tax,
                "home_appreciation": home_r,
                "rent_growth": rent_g,
                "inflation_index": inflation_index,
            }
        )

        # Update state variables
        annual_rent *= (1 + rent_g)
    

    yearly = pd.DataFrame(rows)

    # Economic costs exclude principal (principal is a transfer to equity)
    yearly["owner_economic_cost"] = (
        yearly["interest_paid"]
        + yearly["pmi_paid"]
        + yearly["property_tax"]
        + yearly["maintenance"]
        + yearly["hoa_annual"]
        + yearly["home_insurance"]
    )

    return yearly