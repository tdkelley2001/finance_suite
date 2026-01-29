from dataclasses import dataclass
import numpy as np

from rent_vs_buy.engine.assumptions import Assumptions


@dataclass(frozen=True)
class RatePaths:
    # Each array length must be horizon
    investment_return: np.ndarray
    home_appreciation: np.ndarray
    rent_growth: np.ndarray
    inflation: np.ndarray

    def validate(self, horizon: int) -> None:
        for name, arr in [
            ("investment_return", self.investment_return),
            ("home_appreciation", self.home_appreciation),
            ("rent_growth", self.rent_growth),
            ("inflation", self.inflation),
        ]:
            if len(arr) != horizon:
                raise ValueError(f"{name} length {len(arr)} does not match horizon {horizon}")


class RateProvider:
    def get(self, name: str, year: int) -> float:
        raise NotImplementedError


class DeterministicRateProvider(RateProvider):
    def __init__(self, assump: Assumptions):
        self.assump = assump

    def get(self, name: str, year: int) -> float:
        if name == "investment_return":
            return self.assump.investment_return
        if name == "home_appreciation":
            return self.assump.home_appreciation_rate
        if name == "rent_growth":
            return self.assump.rent_growth_rate
        if name == "inflation":
            return self.assump.inflation
        raise KeyError(name)


class PathRateProvider(RateProvider):
    def __init__(self, paths: RatePaths):
        self.paths = paths

    def get(self, name: str, year: int) -> float:
        idx = year - 1
        if name == "investment_return":
            return float(self.paths.investment_return[idx])
        if name == "home_appreciation":
            return float(self.paths.home_appreciation[idx])
        if name == "rent_growth":
            return float(self.paths.rent_growth[idx])
        if name == "inflation":
            return float(self.paths.inflation[idx])
        raise KeyError(name)