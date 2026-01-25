import pandas as pd
from dataclasses import dataclass
from typing import Optional

from engine.yearly_model import build_yearly_df
from engine.summary import build_summary
from engine.rate_provider import RateProvider


@dataclass
class EngineResult:
    yearly: pd.DataFrame
    summary: dict
    waterfall: pd.DataFrame


def run_engine(assumptions, rate_provider: Optional[RateProvider] = None) -> EngineResult:
    yearly = build_yearly_df(assumptions, rate_provider=rate_provider)
    summary, waterfall = build_summary(yearly, assumptions)
    return EngineResult(yearly=yearly, summary=summary, waterfall=waterfall)