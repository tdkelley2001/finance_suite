from assumptions.app import render_assumptions_manager
from budget.app import render_budget
from emergency_fund.app import render_emergency_fund
from housing_affordability.app import render_housing_affordability
from net_worth.app import render_net_worth
from rent_vs_buy.app import render_rent_vs_buy
from suite.tools import SuiteTool


TOOLS = [
    SuiteTool(
        name="Assumptions",
        title="Assumptions Manager",
        caption="Edit suite-wide modeling defaults used across calculators.",
        render=render_assumptions_manager,
        icon="⚙",
    ),
    SuiteTool(
        name="Net Worth",
        title="Net Worth Tracker",
        caption="Track accounts, assets, liabilities, and balance sheet totals.",
        render=render_net_worth,
        icon="$",
    ),
    SuiteTool(
        name="Budget & Cash Flow",
        title="Monthly Budget",
        caption="A simple, editable view of your monthly cash flow.",
        render=render_budget,
        icon="💰",
    ),
    SuiteTool(
        name="Emergency Fund",
        title="Emergency Fund Calculator",
        caption="Estimate emergency reserves from shared cash flow and liquidity.",
        render=render_emergency_fund,
        icon="EF",
    ),
    SuiteTool(
        name="Housing Affordability",
        title="Housing Affordability",
        caption="Evaluate home affordability against cash flow and cash constraints.",
        render=render_housing_affordability,
        icon="🏠",
    ),
    SuiteTool(
        name="Rent vs Buy",
        title="Rent vs Buy Model",
        caption="Analysis of long-run net worth.",
        render=render_rent_vs_buy,
        icon="📊",
        advice_warning=True,
    ),
]
