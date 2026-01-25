from engine.assumptions import build_assumptions
from engine.engine import run_engine


def deterministic_run(scenario: str, region: str, overrides=None, horizon: int = 30):
    assump = build_assumptions(scenario=scenario, region=region, overrides=overrides, horizon=horizon)
    return run_engine(assump)