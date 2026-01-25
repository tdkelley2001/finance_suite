from copy import deepcopy
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd

# Predefined Monte Carlo profiles
MC_PROFILES = {
    "Baseline": {"param_sd_scale": 1.0, "path_sd_scale": 1.0},
    "Conservative": {"param_sd_scale": 0.75, "path_sd_scale": 0.75},
    "Volatile": {"param_sd_scale": 1.25, "path_sd_scale": 1.25},
    "Stress": {"param_sd_scale": 1.5, "path_sd_scale": 1.75},
}

from engine.assumptions import build_assumptions, Assumptions
from engine.engine import run_engine
from engine.rate_provider import RatePaths, PathRateProvider, DeterministicRateProvider
from samplers.distributions import NormalDist



# Parameter-level uncertainty: sample the per-run constants (means)
DEFAULT_PARAM_DISTS = {
    # Means for rates (constant within each run unless path_uncertainty is also enabled)
    "investment_return": lambda a: NormalDist(a.investment_return, 0.02, clip=(-0.05, 0.20)),
    "home_appreciation_rate": lambda a: NormalDist(a.home_appreciation_rate, 0.02, clip=(-0.10, 0.20)),
    "rent_growth_rate": lambda a: NormalDist(a.rent_growth_rate, 0.015, clip=(0.0, 0.15)),
    "inflation": lambda a: NormalDist(a.inflation, 0.01, clip=(0.0, 0.10)),

    # Non-rate parameters (optional, shows the power of parameter uncertainty)
    "maintenance_pct": lambda a: NormalDist(a.maintenance_pct, 0.003, clip=(0.005, 0.03)),
    "homeowners_insurance_annual": lambda a: NormalDist(a.homeowners_insurance_annual, 300.0, clip=(0.0, None)),
    "hoa_monthly": lambda a: NormalDist(a.hoa_monthly, 50.0, clip=(0.0, None)),
}

# Path-level uncertainty: year-by-year noise around the sampled means
DEFAULT_PATH_SDS = {
    "investment_return": 0.15,     # equity-like volatility
    "home_appreciation": 0.08,
    "rent_growth": 0.05,
    "inflation": 0.015,
}

DEFAULT_PATH_CLIPS = {
    "investment_return": (-0.40, 0.40),
    "home_appreciation": (-0.30, 0.30),
    "rent_growth": (0.0, 0.15),
    "inflation": (0.0, 0.10),
}


def _sample_parameters(base: Assumptions, param_sd_scale: float = 1.0, param_dists=None) -> Assumptions:
    """
    Samples per-run parameters and returns a new Assumptions.
    """
    param_dists = param_dists or DEFAULT_PARAM_DISTS
    sampled = deepcopy(base)

    for field, dist_factory in param_dists.items():
        dist = dist_factory(sampled)
        scaled_dist = NormalDist(
            getattr(sampled, field),
            dist.sd * param_sd_scale,
            clip=dist.clip,
        )
        val = scaled_dist.sample()
        # Handle clips with None upper bound
        if isinstance(val, np.ndarray):
            val = float(val.item())
        if field in {"homeowners_insurance_annual", "hoa_monthly"} and val < 0:
            val = 0.0
        setattr(sampled, field, float(val))

    sampled.validate()
    return sampled


def _sample_paths(assump: Assumptions, horizon: int, path_sd_scale: float = 1.0, path_sds=None) -> RatePaths:
    path_sds = path_sds or DEFAULT_PATH_SDS

    inv = NormalDist(assump.investment_return, path_sds["investment_return"] * path_sd_scale, clip=DEFAULT_PATH_CLIPS["investment_return"]).sample(size=horizon)
    home = NormalDist(assump.home_appreciation_rate, path_sds["home_appreciation"] * path_sd_scale, clip=DEFAULT_PATH_CLIPS["home_appreciation"]).sample(size=horizon)
    rent = NormalDist(assump.rent_growth_rate, path_sds["rent_growth"] * path_sd_scale, clip=DEFAULT_PATH_CLIPS["rent_growth"]).sample(size=horizon)
    infl = NormalDist(assump.inflation, path_sds["inflation"] * path_sd_scale, clip=DEFAULT_PATH_CLIPS["inflation"]).sample(size=horizon)

    paths = RatePaths(
        investment_return=np.asarray(inv, dtype=float),
        home_appreciation=np.asarray(home, dtype=float),
        rent_growth=np.asarray(rent, dtype=float),
        inflation=np.asarray(infl, dtype=float),
    )
    paths.validate(horizon)
    return paths


def monte_carlo_run(
    scenario: str,
    region: str,
    overrides: Optional[Dict],
    horizon: int,
    n_sims: int,
    seed: int,
    mc_profile: str,
    param_sd_scale: float,
    path_sd_scale: float,
    keep_yearly: bool = False,
) -> Tuple[pd.DataFrame, Optional[list]]:
    """
    Returns:
      results_df: one row per simulation
      yearly_list: optional list of yearly DataFrames (large; use sparingly)
    """
    np.random.seed(seed)

    base = build_assumptions(scenario=scenario, region=region, overrides=overrides, horizon=horizon)

    rows = []
    yearly_list = [] if keep_yearly else None

    for _ in range(n_sims):
        assump_i = _sample_parameters(
            base,
            param_sd_scale=param_sd_scale,
        )
        paths = _sample_paths(
            assump_i,
            horizon=horizon,
            path_sd_scale=path_sd_scale,
        )
        provider = PathRateProvider(paths)
        result = run_engine(assump_i, rate_provider=provider)

        rows.append(
            {
                "owner_net_worth": result.summary["owner_net_worth"],
                "renter_net_worth": result.summary["renter_net_worth"],
                "net_worth_diff": result.summary["net_worth_diff"],
            }
        )

        if keep_yearly:
            yearly_list.append(result.yearly)

    return pd.DataFrame(rows), yearly_list