import streamlit as st
from typing import Dict, Optional
import pandas as pd

from rent_vs_buy.samplers.monte_carlo import monte_carlo_run
from rent_vs_buy.ui.run_context import RunContext
from rent_vs_buy.config.config_loader import load_yaml_keys
from rent_vs_buy.engine.assumptions import build_assumptions
from rent_vs_buy.ui.sidebar_assumptions import collect_assumptions
from rent_vs_buy.ui.run_summary import (
    render_model_summary,
    render_assumption_summary,
)
from rent_vs_buy.samplers.deterministic import deterministic_run
from rent_vs_buy.ui.sections import (
    render_net_worth_section,
    render_cashflow_section,
    render_starting_position,
    render_decomposition_section,
    render_mc_summary,
    render_mc_timing,
    render_mc_risk,
    render_mc_sensitivity
)
from rent_vs_buy.ui.mc_metrics import summarize_net_worth_diff


RENT_BASIS_OPTIONS = {
        "Market rent": "market",
        "Match mortgage payment": "match_mortgage",
        "Match total owner cost": "match_owner_cost",
    }

MC_PROFILES = {
    "Baseline": {
        "param_sd_scale": 1.0,
        "path_sd_scale": 1.0,
        "help": "The baseline profile assumes moderate uncertainty around long-term assumptions."
    },
    "Conservative": {
        "param_sd_scale": 0.75,
        "path_sd_scale": 0.75,
        "help": "The conservative profile assumes more stable conditions with smaller swings in outcomes."
    },
    "Volatile": {
        "param_sd_scale": 1.25,
        "path_sd_scale": 1.25,
        "help": "The volatile profile allows larger swings in markets and housing outcomes."
    },
    "Stress": {
        "param_sd_scale": 1.5,
        "path_sd_scale": 1.75,
        "help": "The stress profile explores adverse but plausible scenarios with high uncertainty."
    },
}


def render_rent_vs_buy():
    # ==================================================
    # Page config
    # ==================================================
    st.header("🏠 Rent vs Buy Model")
    st.caption("Analysis of long-run net worth")
    st.warning(
        "This tool is for educational and exploratory purposes only. "
        "It is not financial advice or a recommendation. "
        "Results are highly assumption-dependent and represent hypothetical outcomes, not predictions."
    )


    # ==================================================
    # Deterministic and Monte Carlo runners
    # ==================================================
    @st.cache_data(show_spinner=False)
    def run_deterministic_cached(
            context: RunContext,
            overrides: Optional[Dict]
        ):
        return deterministic_run(
            scenario=context.scenario,
            region=context.region,
            overrides=overrides,
            horizon=context.horizon,
            rent_basis=context.rent_basis,
            married=context.married,
            sell_at_end=context.sell_at_end,
        )

    def run_mc_cached(
        context: RunContext,
        overrides: Optional[Dict],
        n_sims: int,
        seed: int,
        mc_profile: str,
        param_sd_scale: float,
        path_sd_scale: float,
    ):
        return monte_carlo_run(
            scenario=context.scenario,
            region=context.region,
            overrides=overrides,
            horizon=context.horizon,
            rent_basis=context.rent_basis,
            married=context.married,
            sell_at_end=context.sell_at_end,
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
    # Sidebar: Global controls
    # ==================================================
    with st.sidebar:
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

        st.header("Uncertainty")

        include_uncertainty = st.checkbox(
            "Include uncertainty (recommended)",
            value=True,
            help=(
                "When enabled, the model explores many plausible futures instead of assuming "
                "a single outcome. This helps understand risk and variability."
            )
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

        st.header("Active Assumptions")
        context_key = f"{scenario}_{region}_{rent_basis}_{married}_{sell_at_end}"
        overrides, assumption_rows, override_count = collect_assumptions(
            baseline,
            context_key=context_key,
        )

        if include_uncertainty:
            st.divider()
            st.header("Simulation Settings")

            st.caption(
                "Uncertainty profiles control how much uncertainty is applied to future assumptions. "
                "They do not change the baseline scenario, only how widely outcomes are allowed to vary."
            )

            mc_profile = st.selectbox(
                "Uncertainty profile",
                list(MC_PROFILES.keys()),
            )
            st.caption(MC_PROFILES[mc_profile]['help'])

            profile_defaults = MC_PROFILES[mc_profile]

            with st.expander("Advanced uncertainty controls", expanded=False):
                param_sd_scale = st.slider(
                    "Parameter uncertainty scale",
                    min_value=0.25,
                    max_value=3.0,
                    value=profile_defaults["param_sd_scale"],
                    step=0.05,
                    help=(
                        "Controls uncertainty about the long-term assumptions themselves, such as "
                        "average investment returns or home appreciation. Higher values mean the "
                        "future could settle around very different long-term outcomes."
                    )
                )

                path_sd_scale = st.slider(
                    "Path volatility scale",
                    min_value=0.25,
                    max_value=3.0,
                    value=profile_defaults["path_sd_scale"],
                    step=0.05,
                    help=(
                        "Controls how much outcomes fluctuate year to year. "
                        "Higher values mean bumpier paths with larger short-term ups and downs, "
                        "even if long-term averages stay the same."
                    )
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
                    help="Controls reproducibility of simulation runs",
                )
        
        run_button = st.button("Run model", type="primary")


    # ======================================================
    # Main panel
    # ======================================================
    if not run_button:
        st.info("Set inputs in the sidebar and click **Run model**.")
        st.stop()


    # ==================================================
    # Run context
    # ==================================================
    context = RunContext(
        scenario=scenario,
        region=region,
        horizon=horizon,
        rent_basis=rent_basis,
        married=married,
        sell_at_end=sell_at_end,
    )

    render_model_summary(
        context=context,
        rent_basis_label=rent_basis_label,
        override_count=override_count,
    )

    render_assumption_summary(
        override_count=override_count,
        assumption_rows=assumption_rows,
    )

    # ======================================================
    # Model Run
    # ======================================================
    baseline_result = run_deterministic_cached(context, overrides)

    yearly = baseline_result.yearly
    summary = baseline_result.summary
    waterfall = baseline_result.waterfall

    st.subheader("Baseline Projection")
    st.caption(
        "This projection shows what happens if the future unfolds exactly according "
        "to the assumptions shown above. It serves as a reference point for understanding "
        "how owning and renting compare under a single, consistent scenario."
    )

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

    st.divider()

    # ======================================================
    # MONTE CARLO MODE
    # ======================================================
    if include_uncertainty:
        with st.spinner("Running simulation..."):
            df, yearly_list = run_mc_cached(
                context=context,
                overrides=overrides,
                n_sims=n_sims,
                seed=seed,
                mc_profile=mc_profile,
                param_sd_scale=param_sd_scale,
                path_sd_scale=path_sd_scale,
            )

            # Stack all Monte Carlo yearly paths
            mc_yearly = pd.concat(
                [sim_df.assign(sim=i) for i, sim_df in enumerate(yearly_list)],
                ignore_index=True,
            )

            # Net worth difference per simulation-year
            mc_yearly["net_worth_diff"] = (
                mc_yearly["owner_net_worth"] - mc_yearly["renter_net_worth"]
            )

            stats = summarize_net_worth_diff(df)
            det_net_worth_diff = summary["net_worth_diff"]

            st.subheader("Uncertainty & Risk Analysis")
            st.markdown("""
            Instead of assuming a single future, this simulation explores *many plausible futures* by allowing
            key assumptions (like home appreciation, rent growth, and investment returns) to vary over time.

            Each simulation represents one possible path the future could take.  
            The results below summarize how often owning or renting comes out ahead across thousands of such paths.
            These results help compare relative risk and tradeoffs, not predict exact outcomes.
            """)

            tab_summary, tab_timing, tab_risk, tab_sensitivity = st.tabs([
                "Summary",
                "Timing & Probability",
                "Downside Risk",
                "Sensitivity",
            ])

            with tab_summary:
                render_mc_summary(stats, det_net_worth_diff)

            with tab_timing:
                render_mc_timing(mc_yearly)

            with tab_risk:
                render_mc_risk(df)

            with tab_sensitivity:
                render_mc_sensitivity(baseline, det_net_worth_diff, context)