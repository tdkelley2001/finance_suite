from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    scenario: str
    region: str
    horizon: int
    rent_basis: str
    married: bool
    sell_at_end: bool