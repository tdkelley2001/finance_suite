from dataclasses import dataclass
from typing import Any, Dict, Optional
from config_loader import load_yaml


@dataclass
class Assumptions:
    home_price: float
    down_payment_pct: float
    mortgage_rate: float
    mortgage_term: int
    closing_costs_pct: float
    maintenance_pct: float
    hoa_monthly: float
    homeowners_insurance_annual: float
    pmi_rate: float
    pmi_ltv_cutoff: float
    home_appreciation_rate: float
    sell_at_end: bool
    selling_costs_pct: float

    rent_basis: str
    monthly_rent: float
    rent_growth_rate: float
    renters_insurance_annual: float

    horizon: int
    investment_return: float
    inflation: float

    property_tax_pct: float
    married: bool
    capital_gains_tax_rate: float
    capital_gains_exclusion_single: float
    capital_gains_exclusion: float
    investment_tax_drag: float

    def validate(self) -> None:
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.mortgage_term <= 0:
            raise ValueError("mortgage_term must be positive")
        if not (0 <= self.down_payment_pct <= 1):
            raise ValueError("down_payment_pct must be between 0 and 1")
        if self.rent_basis not in {"market", "mortgage_matched"}:
            raise ValueError("rent_basis must be 'market' or 'mortgage_matched'")
        if self.home_price <= 0:
            raise ValueError("home_price must be positive")


def build_assumptions(
    scenario: str,
    region: str,
    overrides: Optional[Dict[str, Any]] = None,
    horizon: int = 30,
) -> Assumptions:
    scenarios = load_yaml("scenarios.yaml")
    regions = load_yaml("regions.yaml")
    globals_ = load_yaml("globals.yaml")

    params: Dict[str, Any] = {}
    params.update(globals_)
    params.update(scenarios[scenario])
    params.update(regions[region])

    if overrides:
        params.update(overrides)

    cap_excl = globals_["capital_gains_exclusion_single"] * (2 if globals_.get("married", False) else 1)

    # Region tilts relative to US baselines, unless overridden explicitly
    if overrides and "home_appreciation_rate" in overrides:
        home_appreciation_rate = float(overrides["home_appreciation_rate"])
    else:
        home_appreciation_tilt = (
            regions[region]["home_appreciation_rate_baseline"]
            - regions["US"]["home_appreciation_rate_baseline"]
        )
        home_appreciation_rate = float(scenarios[scenario]["home_appreciation_rate"] + home_appreciation_tilt)

    if overrides and "rent_growth_rate" in overrides:
        rent_growth_rate = float(overrides["rent_growth_rate"])
    else:
        rent_growth_tilt = (
            regions[region]["rent_growth_rate_baseline"]
            - regions["US"]["rent_growth_rate_baseline"]
        )
        rent_growth_rate = float(scenarios[scenario]["rent_growth_rate"] + rent_growth_tilt)

    assump = Assumptions(
        home_price=float(params["home_price"]),
        down_payment_pct=float(params["down_payment_pct"]),
        mortgage_rate=float(params["mortgage_rate"]),
        mortgage_term=int(params["mortgage_term"]),
        closing_costs_pct=float(params["closing_costs_pct"]),
        maintenance_pct=float(params["maintenance_pct"]),
        hoa_monthly=float(params["hoa_monthly"]),
        homeowners_insurance_annual=float(params["homeowners_insurance_annual"]),
        pmi_rate=float(params["pmi_rate"]),
        pmi_ltv_cutoff=float(params["pmi_ltv_cutoff"]),
        home_appreciation_rate=home_appreciation_rate,
        sell_at_end=bool(params["sell_at_end"]),
        selling_costs_pct=float(params["selling_costs_pct"]),
        rent_basis=str(params["rent_basis"]),
        monthly_rent=float(params["monthly_rent"]),
        rent_growth_rate=rent_growth_rate,
        renters_insurance_annual=float(params["renters_insurance_annual"]),
        horizon=int(horizon),
        investment_return=float(params["investment_return"]),
        inflation=float(params["inflation"]),
        property_tax_pct=float(params["property_tax_pct"]),
        married=bool(globals_.get("married", False)),
        capital_gains_exclusion_single=float(globals_["capital_gains_exclusion_single"]),
        capital_gains_tax_rate=float(globals_["capital_gains_tax_rate"]),
        capital_gains_exclusion=float(cap_excl),
        investment_tax_drag=float(params["investment_tax_drag"]),
    )
    assump.validate()
    return assump