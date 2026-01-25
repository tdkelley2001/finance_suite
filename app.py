import streamlit as st
from typing import Dict, Optional, Tuple, Literal
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config_loader import load_yaml_keys
from engine.assumptions import build_assumptions
from engine.mortgage import mortgage_schedule
from samplers.monte_carlo import monte_carlo_run
from samplers.deterministic import deterministic_run
from samplers.monte_carlo import MC_PROFILES


# ==================================================
# Helpers
# ==================================================
def values_equal(a, b, kind, tol=1e-6):
    if kind in ("percent", "currency"):
        return abs(float(a) - float(b)) < tol
    elif kind == "int":
        return int(a) == int(b)
    elif kind == "bool":
        return bool(a) == bool(b)
    else:
        return a == b


def format_assumption_value(val, kind):
    if kind == "currency":
        return f"${val:,.0f}"
    elif kind == "percent":
        return f"{val:.2%}"
    elif kind == "int":
        return f"{int(val)}"
    elif kind == "bool":
        return "Yes" if val else "No"
    else:
        return str(val)


def highlight_overrides(row):
    if row["Source"] == "Override":
        return ["background-color: #4A587A"] * len(row)
    return [""] * len(row)


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


# ==================================================
# Streamlit tabs
# ==================================================
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


# ==================================================
# Page config
# ==================================================
st.set_page_config(
    page_title="Rent vs Buy Model",
    layout="wide",
)

st.title("🏠 Rent vs Buy Model")
st.caption("Deterministic and Monte Carlo analysis of long-run net worth")
st.warning(
    "This tool is for educational and exploratory purposes only. "
    "It is not financial advice or a recommendation. "
    "Results are highly assumption-dependent and represent hypothetical outcomes, not predictions."
)


# ==================================================
# Cached Monte Carlo runner
# ==================================================
@st.cache_data(show_spinner=False)
def run_mc_cached(
    scenario: str,
    region: str,
    overrides: Optional[Dict],
    horizon: int,
    rent_basis: str,
    married: bool,
    sell_at_end: bool,
    n_sims: int,
    seed: int,
    mc_profile: str,
    param_sd_scale: float,
    path_sd_scale: float,
):
    return monte_carlo_run(
        scenario=scenario,
        region=region,
        overrides=overrides,
        horizon=horizon,
        rent_basis=rent_basis,
        married=married,
        sell_at_end=sell_at_end,
        n_sims=n_sims,
        seed=seed,
        mc_profile=mc_profile,
        param_sd_scale=param_sd_scale,
        path_sd_scale=path_sd_scale,
        keep_yearly=True,
    )


# ==================================================
# Load config-driven options
# ==================================================
scenarios = [s for s in load_yaml_keys("scenarios.yaml") if not s.startswith("_")]
regions = [r for r in load_yaml_keys("regions.yaml") if not r.startswith("_")]


# ==================================================
# Parameter metadata
# ==================================================
PARAM_GROUPS = {
    "Purchase & Financing": [
        ("home_price", "Home price ($)", "currency"),
        ("down_payment_pct", "Down payment (%)", "percent"),
        ("mortgage_rate", "Mortgage rate (%)", "percent"),
        ("mortgage_term", "Mortgage term (years)", "int"),
        ("closing_costs_pct", "Closing costs (%)", "percent"),
        ("pmi_rate", "PMI rate (%)", "percent"),
        ("pmi_ltv_cutoff", "PMI LTV cutoff (%)", "percent"),
    ],
    "Ongoing Owner Costs": [
        ("maintenance_pct", "Maintenance (% of home value)", "percent"),
        ("property_tax_pct", "Property tax (%)", "percent"),
        ("hoa_monthly", "HOA (monthly $)", "currency"),
        ("homeowners_insurance_annual", "Homeowners insurance (annual $)", "currency"),
        ("selling_costs_pct", "Selling costs (%)", "percent"),
    ],
    "Rent Assumptions": [
        ("monthly_rent", "Monthly rent ($)", "currency"),
        ("rent_growth_rate", "Rent growth (%)", "percent"),
        ("renters_insurance_annual", "Renters insurance (annual $)", "currency"),
    ],
    "Investment & Taxes": [
        ("home_appreciation_rate", "Home appreciation rate (%)", "percent"),
        ("capital_gains_tax_rate", "Capital gains tax rate (%)", "percent"),
        ("capital_gains_exclusion_single", "Single capital gains exclusion ($)", "currency"),
        ("investment_return", "Investment return (%)", "percent"),
        ("investment_tax_drag", "Investment tax drag (%)", "percent"),
        ("inflation", "Inflation (%)", "percent"),
    ],
}

OVERRIDE_HELP = {
    "rent_growth_rate": "Annual growth rate applied to rent after year 1",
    "home_appreciation_rate": "Long-run nominal home price appreciation",
    "investment_tax_drag": "Effective annual reduction due to taxes on investments",
    "capital_gains_tax_rate": "Tax rate applied to realized home price gains beyond exclusion",
    "pmi_rate": "Annual PMI cost as a fraction of the original loan balance",
}


# ==================================================
# Sidebar: Global controls
# ==================================================
with st.sidebar:
    st.header("Model Mode")

    mode = st.radio(
        "Run type",
        ["Deterministic", "Monte Carlo"],
        horizontal=True,
        help="Choose between a single deterministic run or a Monte Carlo simulation",
    )

    st.divider()

    st.header("Scenario")

    scenario = st.selectbox(
        "Scenario",
        scenarios,
        index=scenarios.index("base") if "base" in scenarios else 0,
        help="Macroeconomic and housing market assumptions",
    )

    region = st.selectbox(
        "Region",
        regions,
        index=regions.index("US") if "US" in regions else 0,
        help="Regional housing market characteristics",
    )

    horizon = st.slider(
        "Horizon (years)",
        min_value=1,
        max_value=50,
        value=30,
        step=1,
        help="Length of time the rent vs buy decision is evaluated",
    )

    st.header("Model Regime Controls")

    RENT_BASIS_OPTIONS = {
        "Market rent": "market",
        "Match mortgage payment": "match_mortgage",
        "Match total owner cost": "match_owner_cost",
    }

    rent_basis_label = st.selectbox(
        "Rent basis",
        list(RENT_BASIS_OPTIONS.keys()),
        help="Defines how renter housing costs are initialized in year 1",
    )

    rent_basis = RENT_BASIS_OPTIONS[rent_basis_label]

    married = st.checkbox(
        "Married filing jointly",
        value=True,
        help="Controls capital gains exclusion and tax treatment"
    )

    sell_at_end = st.checkbox(
        "Sell home at end of horizon",
        value=True,
        help="If unchecked, home equity remains unrealized"
    )

    st.divider()


    # ==================================================
    # Baseline assumptions (engine-resolved)
    # ==================================================
    baseline = build_assumptions(
        scenario=scenario,
        region=region,
        overrides=None,
        horizon=horizon,
        rent_basis=rent_basis,
        married=married,
        sell_at_end=sell_at_end,
    )

    override_count = 0
    label = "Active Assumptions"
    if override_count > 0:
        label += f" ({override_count} override{'s' if override_count > 1 else ''})"

    st.header(label)

    overrides = {}
    assumption_rows = []

    # --------------------------------------------------
    # Model Regime rows (prepend)
    # --------------------------------------------------
    for group, params in PARAM_GROUPS.items():
        with st.expander(group, expanded=False):
            for name, label, kind in params:
                base_val = getattr(baseline, name)

                # --- Render widget with BASELINE value ---
                if kind == "percent":
                    ui_val = st.number_input(
                        label,
                        value=float(base_val) * 100,
                        step=0.1,
                        help=OVERRIDE_HELP.get(name, None),
                    ) / 100

                elif kind == "currency":
                    ui_val = st.number_input(
                        label,
                        value=float(base_val),
                        step=100.0,
                        help=OVERRIDE_HELP.get(name, None),
                    )

                elif kind == "int":
                    ui_val = st.number_input(
                        label,
                        value=int(base_val),
                        step=1,
                        help=OVERRIDE_HELP.get(name, None),
                    )

                elif kind == "bool":
                    ui_val = st.checkbox(
                        label,
                        value=bool(base_val),
                        help=OVERRIDE_HELP.get(name, None),
                    )

                else:
                    raise ValueError(f"Unsupported parameter type: {kind}")

                # --- Override detection (stateless, safe) ---
                source = "Baseline"
                if not values_equal(ui_val, base_val, kind):
                    overrides[name] = ui_val
                    source = "Override"
                    st.caption("✏️ Overridden from scenario baseline")

                assumption_rows.append(
                    {
                        "Group": group,
                        "Parameter": label,
                        "Value": format_assumption_value(ui_val, kind),
                        "Source": source,
                    }
                )

    overrides = overrides or None
    override_count = len(overrides) if overrides else 0

    if mode == "Monte Carlo":
        st.divider()
        st.header("Simulation Settings")

        mc_profile = st.selectbox(
            "Monte Carlo profile",
            list(MC_PROFILES.keys()),
            index=0,
        )

        profile_defaults = MC_PROFILES[mc_profile]

        with st.expander("Advanced uncertainty controls", expanded=False):
            param_sd_scale = st.slider(
                "Parameter uncertainty scale",
                min_value=0.25,
                max_value=3.0,
                value=profile_defaults["param_sd_scale"],
                step=0.05,
            )

            path_sd_scale = st.slider(
                "Path volatility scale",
                min_value=0.25,
                max_value=3.0,
                value=profile_defaults["path_sd_scale"],
                step=0.05,
            )

            n_sims = st.slider(
                "Number of simulations",
                min_value=1_000,
                max_value=20_000,
                value=5_000,
                step=1_000,
            )

            seed = st.number_input(
                "Random seed",
                value=42,
                step=1,
                help="Controls reproducibility of Monte Carlo runs",
            )
    
    run_button = st.button("Run model", type="primary")


# ======================================================
# Main panel
# ======================================================
if not run_button:
    st.info("Set inputs in the sidebar and click **Run model**.")
    st.stop()


# ======================================================
# Run context summary (lightweight, non-intrusive)
# ======================================================
st.subheader("Model Run Summary")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Scenario", scenario)
c2.metric("Region", region)
c3.metric("Horizon", f"{horizon} years")
c4.metric("Overrides", override_count)

c5, c6, c7, = st.columns(3)
c5.metric("Rent Basis", rent_basis_label)
c6.metric("Married", "Yes" if married else "No")
c7.metric("Sell at End", "Yes" if sell_at_end else "No")


st.caption(
    "Results below reflect the current scenario baseline plus any manual overrides. "
    "Use the assumptions summary to audit inputs."
)

st.divider()

# ======================================================
# Active assumptions summary table
# ======================================================
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


# ======================================================
# Helper: yearly table formatting
# ======================================================
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


# ======================================================
# DETERMINISTIC MODE
# ======================================================
if mode == "Deterministic":
    result = deterministic_run(
        scenario=scenario,
        region=region,
        overrides=overrides,
        horizon=horizon,
        rent_basis=rent_basis,
        married=married,
        sell_at_end=sell_at_end,
    )

    yearly = result.yearly
    summary = result.summary
    waterfall = result.waterfall

    st.subheader("Deterministic Model Results")

    tab_wealth, tab_cashflow, tab_start, tab_decompose = st.tabs([
        "Net Worth Outcomes",
        "Cashflow & Affordability",
        "Starting Position",
        "Why This Happens",
    ])

    with tab_wealth:
        render_net_worth_section(yearly, summary, horizon)

    with tab_cashflow:
        render_cashflow_section(yearly)
    
    with tab_start:
        render_starting_position(baseline, yearly)

    with tab_decompose:
        render_decomposition_section(waterfall, yearly)

# ======================================================
# MONTE CARLO MODE
# ======================================================
else:
    with st.spinner("Running Monte Carlo simulation..."):
        df, yearly_list = run_mc_cached(
            scenario=scenario,
            region=region,
            overrides=overrides,
            horizon=horizon,
            rent_basis=rent_basis,
            married=married,
            sell_at_end=sell_at_end,
            n_sims=n_sims,
            seed=seed,
            mc_profile=mc_profile,
            param_sd_scale=param_sd_scale,
            path_sd_scale=path_sd_scale,
        )

        # Stack all Monte Carlo yearly paths
        mc_yearly = pd.concat(
            [
                sim_df.assign(sim=i)
                for i, sim_df in enumerate(yearly_list)
            ],
            ignore_index=True,
        )

        # Net worth difference per simulation-year
        mc_yearly["net_worth_diff"] = (
            mc_yearly["owner_net_worth"] - mc_yearly["renter_net_worth"]
        )

        # Deterministic baseline for Monte Carlo reference
        det_result = deterministic_run(
            scenario=scenario,
            region=region,
            overrides=overrides,
            horizon=horizon,
            rent_basis=rent_basis,
            married=married,
            sell_at_end=sell_at_end,
        )

        det_net_worth_diff = det_result.summary["net_worth_diff"]

        st.subheader("Monte Carlo Simulation Results")

        tab_summary, tab_timing, tab_risk, tab_sensitivity = st.tabs([
            "Summary",
            "Timing & Probability",
            "Downside Risk",
            "Sensitivity",
        ])

        with tab_summary:
            st.subheader("Monte Carlo Summary")

            # -------------------------------
            # Baseline reference (anchor)
            # -------------------------------
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

            prob_owner_wins = (df["net_worth_diff"] > 0).mean()
            median_diff = df["net_worth_diff"].median()
            p10 = df["net_worth_diff"].quantile(0.10)
            p90 = df["net_worth_diff"].quantile(0.90)

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Probability Owning Wins",
                f"{prob_owner_wins:.1%}",
                help="Fraction of simulated futures where owning ends with higher net worth than renting"
            )
            col2.metric("Median Advantage",f"${median_diff:,.0f}")
            col3.metric("10th Percentile", f"${p10:,.0f}")
            col4.metric("90th Percentile", f"${p90:,.0f}")

        with tab_timing:
            st.subheader("Probability Owning Wins Over Time")

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

        with tab_risk:
            st.subheader("Downside Risk")

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

        with tab_sensitivity:
            st.subheader("Sensitivity Analysis (What Matters Most)")

            base_diff = det_net_worth_diff

            SENS_PARAMS = [
                ("home_appreciation_rate", "Home appreciation"),
                ("investment_return", "Investment return"),
                ("rent_growth_rate", "Rent growth"),
                ("mortgage_rate", "Mortgage rate"),
                ("maintenance_pct", "Maintenance cost"),
            ]

            impacts = []

            for param, label in SENS_PARAMS:
                base_val = getattr(baseline, param)
                bump = 0.01 if "rate" in param or "pct" in param else base_val * 0.01

                for direction, sign in [("Down", -1), ("Up", 1)]:
                    overrides_sens = {param: base_val + sign * bump}

                    res = deterministic_run(
                        scenario=scenario,
                        region=region,
                        overrides=overrides_sens,
                        horizon=horizon,
                        rent_basis=rent_basis,
                        married=married,
                        sell_at_end=sell_at_end,
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