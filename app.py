import streamlit as st
from typing import Dict, Optional, Tuple
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from config_loader import load_yaml_keys
from engine.assumptions import build_assumptions
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
# Page config
# ==================================================
st.set_page_config(
    page_title="Rent vs Buy Model",
    layout="wide",
)

st.title("🏠 Rent vs Buy Model")
st.caption("Deterministic and Monte Carlo analysis of long-run net worth")


# ==================================================
# Cached Monte Carlo runner
# ==================================================
@st.cache_data(show_spinner=False)
def run_mc_cached(
    scenario: str,
    region: str,
    overrides: Optional[Dict],
    horizon: int,
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
        n_sims=n_sims,
        seed=seed,
        mc_profile=mc_profile,
        param_sd_scale=param_sd_scale,
        path_sd_scale=path_sd_scale,
        keep_yearly=False,
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
    ],
    "Selling Costs": [
        ("sell_at_end", "Sell at end of horizon", "bool"),
        ("selling_costs_pct", "Selling costs (%)", "percent"),
    ],
    "Rent Assumptions": [
        ("monthly_rent", "Monthly rent ($)", "currency"),
        ("rent_growth_rate", "Rent growth (%)", "percent"),
        ("renters_insurance_annual", "Renters insurance (annual $)", "currency"),
    ],
    "Investment & Taxes": [
        ("home_appreciation_rate", "Home appreciation rate (%)", "percent"),
        ("married", "Married filing jointly", "bool"),
        ("capital_gains_tax_rate", "Capital gains tax rate (%)", "percent"),
        ("capital_gains_exclusion_single", "Single capital gains exclusion ($)", "currency"),
        ("investment_return", "Investment return (%)", "percent"),
        ("investment_tax_drag", "Investment tax drag (%)", "percent"),
        ("inflation", "Inflation (%)", "percent"),
    ],
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
    )

    st.divider()

    st.header("Scenario")

    scenario = st.selectbox(
        "Scenario",
        scenarios,
        index=scenarios.index("base") if "base" in scenarios else 0,
    )

    region = st.selectbox(
        "Region",
        regions,
        index=regions.index("US") if "US" in regions else 0,
    )

    horizon = st.slider(
        "Horizon (years)",
        min_value=1,
        max_value=50,
        value=30,
        step=1,
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
    )

    st.header("Active Assumptions")

    overrides = {}
    assumption_rows = []

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
                    ) / 100

                elif kind == "currency":
                    ui_val = st.number_input(
                        label,
                        value=float(base_val),
                        step=100.0,
                    )

                elif kind == "int":
                    ui_val = st.number_input(
                        label,
                        value=int(base_val),
                        step=1,
                    )

                elif kind == "bool":
                    ui_val = st.checkbox(
                        label,
                        value=bool(base_val),
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

    if mode == "Monte Carlo":
        st.divider()
        st.header("Simulation Settings")

        mc_profile = st.selectbox(
            "Monte Carlo profile",
            list(MC_PROFILES.keys()),
            index=0,
        )

        profile_defaults = MC_PROFILES[mc_profile]

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
# Active assumptions summary table
# ======================================================
st.subheader("Active Assumptions Summary")

assumptions_df = pd.DataFrame(assumption_rows)

styled = (
    assumptions_df
    .style
    .apply(highlight_overrides, axis=1)
)

st.dataframe(styled, use_container_width=True)


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
    )

    yearly = result.yearly
    summary = result.summary
    waterfall = result.waterfall

    col1, col2, col3 = st.columns(3)
    col1.metric("Owner Net Worth", f"${summary['owner_net_worth']:,.0f}")
    col2.metric("Renter Net Worth", f"${summary['renter_net_worth']:,.0f}")
    col3.metric("Owner − Renter", f"${summary['net_worth_diff']:,.0f}")

    st.divider()

    st.subheader("Net Worth Over Time")

    path_df = yearly[["year", "owner_net_worth", "renter_net_worth"]].melt(
        id_vars="year",
        var_name="Type",
        value_name="Net Worth",
    )

    fig = px.line(path_df, x="year", y="Net Worth", color="Type")
    st.plotly_chart(fig, use_container_width=True)

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

# ======================================================
# MONTE CARLO MODE
# ======================================================
else:
    df, _ = run_mc_cached(
        scenario=scenario,
        region=region,
        overrides=overrides,
        horizon=horizon,
        n_sims=n_sims,
        seed=seed,
        mc_profile=mc_profile,
        param_sd_scale=param_sd_scale,
        path_sd_scale=path_sd_scale,
    )

    prob_owner_wins = (df["net_worth_diff"] > 0).mean()
    median_diff = df["net_worth_diff"].median()
    p10 = df["net_worth_diff"].quantile(0.10)
    p90 = df["net_worth_diff"].quantile(0.90)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Probability Owning Wins", f"{prob_owner_wins:.1%}")
    col2.metric("Median Advantage", f"${median_diff:,.0f}")
    col3.metric("10th Percentile", f"${p10:,.0f}")
    col4.metric("90th Percentile", f"${p90:,.0f}")

    st.divider()

    st.subheader("Net Worth Difference Distribution")

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