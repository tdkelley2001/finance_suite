import pandas as pd

from rent_vs_buy.engine.assumptions import Assumptions


def build_summary(yearly: pd.DataFrame, assump: Assumptions):
    end = yearly.iloc[-1]

    sale_price = float(end["home_value"])
    selling_costs = sale_price * assump.selling_costs_pct
    closing_costs = assump.home_price * assump.closing_costs_pct

    # Inflation adjustment for exclusion using realized inflation index
    inflation_index_end = float(end.get("inflation_index", (1 + assump.inflation) ** assump.horizon))
    capital_gain_exclusion = assump.capital_gains_exclusion * inflation_index_end

    gain = sale_price - (assump.home_price + closing_costs) - selling_costs
    taxable_gain = max(0.0, gain - capital_gain_exclusion)
    cap_gains_tax = taxable_gain * assump.capital_gains_tax_rate
    net_sale = sale_price - selling_costs - cap_gains_tax

    if assump.sell_at_end:
        owner_net = net_sale - float(end["mortgage_balance"])
    else:
        owner_net = float(end["owner_net_worth"])

    renter_net = float(end["renter_net_worth"])

    # Opportunity cost of down payment using realized investment path
    dp_amount = assump.home_price * assump.down_payment_pct
    dp_growth = dp_amount
    for r in yearly["investment_return_after_tax"].values:
        dp_growth *= (1 + float(r))
    opportunity_cost = dp_growth - dp_amount

    # Waterfall based on economic costs, not cash outflow
    waterfall = pd.DataFrame(
        [
            ("Renter Net Worth", renter_net),
            ("Net Home Appreciation (after selling costs and CG tax)", net_sale - assump.home_price),
            ("Principal Paydown", float(yearly["principal_paid"].sum())),
            ("Mortgage Interest", -float(yearly["interest_paid"].sum())),
            ("Owner Carrying Costs (economic)", -float(yearly["owner_economic_cost"].sum())),
            ("Opportunity Cost of Down Payment", -float(opportunity_cost)),
            ("Owner Net Worth", owner_net),
        ],
        columns=["category", "value"],
    )

    summary = {
        "owner_net_worth": owner_net,
        "renter_net_worth": renter_net,
        "net_worth_diff": owner_net - renter_net,
        "inflation_index_end": inflation_index_end,
    }

    return summary, waterfall