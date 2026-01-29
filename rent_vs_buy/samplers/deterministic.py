from rent_vs_buy.engine.assumptions import build_assumptions
from rent_vs_buy.engine.engine import run_engine


def deterministic_run(
        scenario: str,
        region: str,
        overrides=None,
        horizon: int = 30,
        rent_basis: str = "market",
        married: bool = False,
        sell_at_end: bool = True
    ):
    assump = build_assumptions(
        scenario=scenario,
        region=region,
        overrides=overrides,
        horizon=horizon,
        rent_basis=rent_basis,
        married=married,
        sell_at_end=sell_at_end
    )
    return run_engine(assump)