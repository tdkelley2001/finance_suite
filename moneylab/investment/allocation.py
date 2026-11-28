"""Complete policy weights and exact opening-value apportionment."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, localcontext

from moneylab.domain.values import decimal_sum, decimal_value, distinct_records, identifier
from moneylab.economics.rates import CALCULATION_CONTEXT


ZERO = Decimal(0)
ONE = Decimal(1)
OPENING_QUANTUM = Decimal("0.00000001")


def fraction(value: Decimal) -> None:
    decimal_value(value, minimum=0)
    if value > ONE:
        raise ValueError("allocation fractions cannot exceed one")


@dataclass(frozen=True, slots=True)
class SleeveWeight:
    sleeve_id: str
    weight: Decimal

    def __post_init__(self):
        identifier(self.sleeve_id)
        fraction(self.weight)


@dataclass(frozen=True, slots=True)
class Allocation:
    weights: tuple[SleeveWeight, ...]

    def __post_init__(self):
        weights = distinct_records(self.weights, SleeveWeight, key=lambda item: item.sleeve_id)
        if decimal_sum(item.weight for item in weights) != ONE:
            raise ValueError("complete allocation weights must sum to one")
        object.__setattr__(self, "weights", weights)

    def require_destinations(self, sleeve_ids: set[str]) -> None:
        if {entry.sleeve_id for entry in self.weights} != sleeve_ids:
            raise ValueError("allocation must explicitly cover every modeled sleeve, including zero weights")


def apportion(total: Decimal, weights: dict[str | None, Decimal]) -> dict[str | None, Decimal]:
    """Allocate an exact total, including an explicit None bucket when undisclosed."""
    decimal_value(total, minimum=0)
    for weight in weights.values():
        fraction(weight)
    if decimal_sum(weights.values()) != ONE:
        raise ValueError("apportionment requires complete weights")
    with localcontext(CALCULATION_CONTEXT):
        ideal = {key: total * weight for key, weight in weights.items()}
        rounded = {key: value.quantize(OPENING_QUANTUM, rounding=ROUND_DOWN)
                   for key, value in ideal.items()}
        units = int((total - sum(rounded.values(), start=ZERO)) / OPENING_QUANTUM)
        ranked = sorted(ideal, key=lambda key: (-(ideal[key] - rounded[key]), key is None, key or ""))
        for key in ranked[:units]:
            rounded[key] += OPENING_QUANTUM
    return rounded
