import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from rent_vs_buy.engine.mortgage import mortgage_schedule
from rent_vs_buy.samplers.deterministic import deterministic_run


CURRENCY_COLS = {
    "home_value",
    "mortgage_balance",
    "principal_paid",
    "interest_paid",
    "pmi_paid",
    "property_tax",
    "maintenance",
    "hoa_annual",
    "home_insurance",
    "annual_rent",
    "renters_insurance",
    "owner_cash_outflow",
    "renter_cash_outflow",
    "renter_surplus",
    "renter_balance",
    "owner_net_worth",
    "renter_net_worth",
    "owner_economic_cost",
}

PERCENT_COLS = {
    "inflation_rate",
    "investment_return",
    "investment_return_after_tax",
    "home_appreciation",
    "rent_growth",
    "ltv",
}

INDEX_COLS = {
    "inflation_index",
}

SENS_PARAMS = [
        ("home_appreciation_rate", "Home appreciation"),
        ("investment_return", "Investment return"),
        ("rent_growth_rate", "Rent growth"),
        ("mortgage_rate", "Mortgage rate"),
        ("maintenance_pct", "Maintenance cost"),
    ]

def format_yearly_df(df: pd.DataFrame):
    fmt = {}
    for col in df.columns:
        if col in CURRENCY_COLS:
            fmt[col] = "${:,.0f}"
        elif col in PERCENT_COLS:
            fmt[col] = "{:.2%}"
        elif col in INDEX_COLS:
            fmt[col] = "{:.3f}"
    return df.style.format(fmt)


def render_net_worth_section(yearly, summary, horizon):
    st.subheader(rf"Ending Position (Year {horizon})")

    col1, col2, col3 = st.columns(3)
    col1.metric("Owner Net Worth", f"${summary['owner_net_worth']:,.0f}")
    col2.metric("Renter Net Worth", f"${summary['renter_net_worth']:,.0f}")
    col3.metric("Owner − Renter", f"${summary['net_worth_diff']:,.0f}")

    # Net worth crossover
    nw_diff = yearly["owner_net_worth"] - yearly["renter_net_worth"]
    nw_cross = yearly.loc[nw_diff >= 0, "year"]
    nw_year = int(nw_cross.iloc[0]) if not nw_cross.empty else None

    st.metric(
        "Net Worth Breakeven Year",
        f"Year {nw_year}" if nw_year else "No breakeven in horizon",
    )

    st.divider()
    st.subheader("Net Worth Over Time")

    path_df = yearly[["year", "owner_net_worth", "renter_net_worth"]].melt(
        id_vars="year",
        var_name="Type",
        value_name="Net Worth",
    )

    fig = px.line(path_df, x="year", y="Net Worth", color="Type")
    st.plotly_chart(fig, use_container_width=True)


def render_cashflow_section(yearly):
    # Cashflow crossover
    cf_diff = yearly["owner_cash_outflow"] - yearly["renter_cash_outflow"]
    cf_cross = yearly.loc[cf_diff <= 0, "year"]
    cf_year = int(cf_cross.iloc[0]) if not cf_cross.empty else None

    st.metric(
        "Cashflow Breakeven Year",
        f"Year {cf_year}" if cf_year else "No breakeven in horizon",
    )

    st.divider()

    st.subheader("Annual Cash Outflow Over Time")

    cf_df = yearly[[
        "year",
        "owner_cash_outflow",
        "renter_cash_outflow",
    ]].melt(
        id_vars="year",
        var_name="Type",
        value_name="Annual Cash Outflow",
    )

    cf_df["Type"] = cf_df["Type"].map({
        "owner_cash_outflow": "Owner",
        "renter_cash_outflow": "Renter",
    })

    fig = px.line(cf_df, x="year", y="Annual Cash Outflow", color="Type")
    fig.update_layout(yaxis_title="Annual Cash Outflow ($)")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Owner Cost Composition Over Time")

    cost_cols = [
        "interest_paid",
        "pmi_paid",
        "property_tax",
        "maintenance",
        "hoa_annual",
        "home_insurance",
    ]

    cost_df = yearly[["year"] + cost_cols].melt(
        id_vars="year",
        var_name="Cost Type",
        value_name="Annual Cost",
    )

    cost_labels = {
        "interest_paid": "Mortgage Interest",
        "pmi_paid": "PMI",
        "property_tax": "Property Tax",
        "maintenance": "Maintenance",
        "hoa_annual": "HOA",
        "home_insurance": "Insurance",
    }

    cost_df["Cost Type"] = cost_df["Cost Type"].map(cost_labels)

    fig = px.area(
        cost_df,
        x="year",
        y="Annual Cost",
        color="Cost Type",
    )

    fig.update_layout(yaxis_title="Annual Cost ($)")
    st.plotly_chart(fig, use_container_width=True)


def render_starting_position(baseline, yearly):
    st.subheader("Starting Position (Year 0)")

    dp_amount = baseline.home_price * baseline.down_payment_pct
    initial_mortgage = baseline.home_price - dp_amount
    initial_equity = dp_amount
    initial_renter_balance = baseline.home_price * (
        baseline.down_payment_pct + baseline.closing_costs_pct
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Owner**")
        st.metric("Home Price", f"${baseline.home_price:,.0f}")
        st.metric("Down Payment", f"${dp_amount:,.0f}")
        st.metric("Initial Mortgage Balance", f"${initial_mortgage:,.0f}")
        st.metric("Initial Home Equity", f"${initial_equity:,.0f}")

    with c2:
        st.markdown("**Renter**")
        st.metric("Initial Investable Balance", f"${initial_renter_balance:,.0f}")
        st.metric("Initial Annual Rent", f"${yearly.loc[0, 'annual_rent']:,.0f}")

    st.subheader("Initial Monthly Housing Cost")

    # Mortgage payment (annual → monthly)
    mortgage_df, annual_mortgage_payment, _ = mortgage_schedule(baseline)
    monthly_mortgage_payment = annual_mortgage_payment / 12
    monthly_rent = yearly.loc[0, "annual_rent"] / 12
    
    c1, c2 = st.columns(2)
    c1.metric("Monthly Mortgage Payment", f"${monthly_mortgage_payment:,.0f}")
    c2.metric("Monthly Rent", f"${monthly_rent:,.0f}")


def render_decomposition_section(waterfall, yearly):
    st.subheader("Economic Decomposition")

    fig = go.Figure(
        go.Waterfall(
            x=waterfall["category"],
            y=waterfall["value"],
            measure=[
                "absolute",
                "relative",
                "relative",
                "relative",
                "relative",
                "relative",
                "total",
            ],
        )
    )

    fig.update_layout(yaxis_title="Net Worth ($)", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Full yearly detail"):
        st.dataframe(format_yearly_df(yearly), use_container_width=True)


def render_mc_summary(stats, det_net_worth_diff):
    st.subheader("Monte Carlo Summary")
    st.caption(
        "These metrics summarize outcomes across all simulated futures. "
        "They describe *how often* owning or renting wins, not what will happen in any single future."
    )

    st.markdown("### Baseline reference (deterministic)")

    st.metric(
        "Deterministic Net Worth Difference",
        f"${det_net_worth_diff:,.0f}",
    )

    st.caption(
        "This is the single-scenario outcome before introducing uncertainty. "
        "Monte Carlo results below show how outcomes vary around this baseline."
    )

    st.divider()

    cols = st.columns(4)
    cols[0].metric(
        "Probability Owning Wins",
        f"{stats['prob_owner_wins']:.1%}",
        help="Fraction of simulated futures where owning ends with higher net worth than renting"
    )
    cols[1].metric("Median Advantage",f"${stats['median']:,.0f}")
    cols[2].metric("10th Percentile", f"${stats['p10']:,.0f}")
    cols[3].metric("90th Percentile", f"${stats['p90']:,.0f}")


def render_mc_timing(mc_yearly):
    st.subheader("Probability Owning Wins Over Time")
    st.caption(
            "Shows how the probability of owning outperforming renting evolves over time "
            "across all simulated futures."
        )

    prob_df = (
        mc_yearly
        .groupby("year")["net_worth_diff"]
        .apply(lambda s: (s > 0).mean())
        .reset_index(name="prob_owner_wins")
    )

    fig = px.line(
        prob_df,
        x="year",
        y="prob_owner_wins",
        labels={"prob_owner_wins": "Probability Owning Wins"},
    )
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Shows how the likelihood of owning outperforming renting evolves over time across simulated futures. "
        "Probabilities are based on pre-sale equity at each year. "
        "Final realized outcomes (after selling costs and taxes) are shown in the Summary tab."
    )

    st.subheader("Net Worth Advantage Over Time (Uncertainty Bands)")

    band_df = (
        mc_yearly
        .groupby("year")["net_worth_diff"]
        .quantile([0.10, 0.50, 0.90])
        .unstack()
        .reset_index()
        .rename(columns={0.10: "p10", 0.50: "median", 0.90: "p90"})
    )

    fig = go.Figure()
    fig.add_traces([
        go.Scatter(
            x=band_df["year"],
            y=band_df["p90"],
            line=dict(width=0),
            showlegend=False,
        ),
        go.Scatter(
            x=band_df["year"],
            y=band_df["p10"],
            fill="tonexty",
            name="10–90% range",
        ),
        go.Scatter(
            x=band_df["year"],
            y=band_df["median"],
            name="Median outcome",
            line=dict(width=3),
        ),
    ])

    fig.update_layout(
        yaxis_title="Owner − Renter Net Worth ($)",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "The shaded region shows the middle 80% of outcomes. "
        "The line shows the typical (median) advantage of owning over time."
    )


def render_mc_risk(df):
    st.subheader("Downside Risk")
    st.caption(
        "Focuses on unfavorable but plausible outcomes to help understand downside risk, "
        "not worst-case extremes."
    )

    prob_owner_loses = (df["net_worth_diff"] < 0).mean()
    p10 = df["net_worth_diff"].quantile(0.10)
    p05 = df["net_worth_diff"].quantile(0.05)

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Chance Owning Underperforms",
        f"{prob_owner_loses:.1%}",
    )

    col2.metric(
        "Worst 1-in-10 Outcome",
        f"${p10:,.0f}",
    )

    col3.metric(
        "Worst 1-in-20 Outcome",
        f"${p05:,.0f}",
    )

    st.caption(
        "These metrics focus on adverse but plausible outcomes. "
        "For example, the 10th percentile represents a poor outcome that occurs roughly 1 in 10 simulations."
    )

    st.divider()

    st.subheader("Distribution of Net Worth Difference")

    fig = px.histogram(df, x="net_worth_diff", nbins=80, marginal="box")
    fig.add_vline(x=0, line_dash="dash", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Summary statistics"):
        st.dataframe(
            df["net_worth_diff"]
            .describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
            .to_frame("Net Worth Difference")
            .style.format("${:,.0f}")
        )


def render_mc_sensitivity(baseline, det_net_worth_diff, context):
    st.subheader("Sensitivity Analysis (What Matters Most)")
    st.caption(
        "Shows which assumptions have the largest impact on results when nudged up or down slightly, "
        "holding everything else constant."
    )

    base_diff = det_net_worth_diff

    impacts = []

    for param, label in SENS_PARAMS:
        base_val = getattr(baseline, param)
        bump = 0.01 if "rate" in param or "pct" in param else base_val * 0.01

        for direction, sign in [("Down", -1), ("Up", 1)]:
            overrides_sens = {param: base_val + sign * bump}

            res = deterministic_run(
                scenario=context.scenario,
                region=context.region,
                overrides=overrides_sens,
                horizon=context.horizon,
                rent_basis=context.rent_basis,
                married=context.married,
                sell_at_end=context.sell_at_end,
            )

            impacts.append({
                "Parameter": label,
                "Direction": direction,
                "Impact": res.summary["net_worth_diff"] - base_diff,
            })

    impact_df = pd.DataFrame(impacts)

    fig = px.bar(
        impact_df,
        x="Impact",
        y="Parameter",
        color="Direction",
        orientation="h",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Each bar shows how changing one assumption at a time affects the final net worth difference. "
        "Longer bars indicate assumptions that matter more."
    )