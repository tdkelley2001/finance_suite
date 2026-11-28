"""Resolve one nominal investment return without portfolio state or posting."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum

from moneylab.domain.values import (
    Revision, currency_code, decimal_sum, decimal_value, distinct_records, identifier,
)
from moneylab.economics import EconomicPath, SeriesKind
from moneylab.economics.rates import (
    CALCULATION_CONTEXT, monthly_effective_rate, validate_annual_effective_rate,
)

from .allocation import ONE, ZERO, fraction
from .taxonomy import DEFAULT_TAXONOMY, ExposureTaxonomy


class CostKind(str, Enum):
    FUND_EXPENSE = "fund_expense"
    ADVISORY_FEE = "advisory_fee"


def annual_fee(value: Decimal | None) -> None:
    if value is not None:
        decimal_value(value, minimum=0)
        if value >= ONE:
            raise ValueError("separate annual fees must be smaller than one")


@dataclass(frozen=True, slots=True)
class ReturnConvention:
    """Nominal total return in the stated currency with itemized embedded costs."""

    currency: str
    embedded_costs: tuple[CostKind, ...] = ()

    def __post_init__(self):
        currency_code(self.currency)
        costs = tuple(self.embedded_costs)
        if any(not isinstance(cost, CostKind) for cost in costs) or len(set(costs)) != len(costs):
            raise ValueError("embedded costs must be distinct supported cost categories")
        object.__setattr__(self, "embedded_costs", tuple(sorted(costs, key=lambda item: item.value)))

    def require_separate(self, cost: CostKind, annual_fraction: Decimal | None) -> None:
        if annual_fraction and cost in self.embedded_costs:
            raise ValueError(f"separate {cost.value} would double count an embedded cost")


@dataclass(frozen=True, slots=True)
class SeriesExposure:
    exposure_id: str
    series_id: str
    weight: Decimal = ONE

    def __post_init__(self):
        identifier(self.exposure_id)
        identifier(self.series_id)
        fraction(self.weight)
        if not self.weight:
            raise ValueError("omit zero-weight economic series from a return mapping")


@dataclass(frozen=True, slots=True)
class ReturnTreatment:
    convention: ReturnConvention
    series: tuple[SeriesExposure, ...] = ()
    annual_effective_rate: Decimal | None = None
    constant_exposure_id: str | None = None
    mapping_revision: Revision | None = None

    def __post_init__(self):
        if not isinstance(self.convention, ReturnConvention):
            raise ValueError("a nominal total-return convention is required")
        if self.mapping_revision is not None and not isinstance(self.mapping_revision, Revision):
            raise ValueError("expected a return mapping revision")
        series = distinct_records(self.series, SeriesExposure, key=lambda item: item.series_id)
        if bool(series) == (self.annual_effective_rate is not None):
            raise ValueError("provide exactly one series mapping or explicit annual effective rate")
        if series:
            if self.constant_exposure_id is not None or decimal_sum(item.weight for item in series) != ONE:
                raise ValueError("series weights must sum to one and have no constant exposure")
        else:
            validate_annual_effective_rate(self.annual_effective_rate)
            if self.constant_exposure_id is not None:
                identifier(self.constant_exposure_id)
        object.__setattr__(self, "series", series)

    def exposure_weights(self) -> dict[str | None, Decimal]:
        if not self.series:
            return {self.constant_exposure_id: ONE}
        ids = sorted({item.exposure_id for item in self.series})
        return {key: decimal_sum(item.weight for item in self.series if item.exposure_id == key) for key in ids}

    def validate_convention(self, currency: str, taxonomy: ExposureTaxonomy) -> None:
        if self.convention.currency != currency:
            raise ValueError(f"returns must be expressed in the projection currency {currency}")
        for key in self.exposure_weights():
            if key is not None:
                taxonomy.require(key)

    def validate(self, currency: str, taxonomy: ExposureTaxonomy, path: EconomicPath | None) -> None:
        self.validate_convention(currency, taxonomy)
        if self.series:
            available = {} if path is None else {item.id: item.kind for item in path.series}
            for item in self.series:
                if available.get(item.series_id) is not SeriesKind.INVESTMENT_RETURN:
                    raise ValueError(f"{item.series_id} must identify an investment return series on the selected path")


def realized_return(
    treatment: ReturnTreatment, *, currency: str, taxonomy: ExposureTaxonomy = DEFAULT_TAXONOMY,
    path: EconomicPath | None = None, month_on: date | None = None,
) -> Decimal:
    """Resolve a direct, fixed composite, or constant monthly total return."""
    treatment.validate(currency, taxonomy, path)
    with localcontext(CALCULATION_CONTEXT):
        if not treatment.series:
            return monthly_effective_rate(treatment.annual_effective_rate)
        if type(month_on) is not date or month_on.day != 1 or not path.start_on <= month_on < path.end_before:
            raise ValueError("a realized return requires a covered first-of-month observation")
        offset = (month_on.year - path.start_on.year) * 12 + month_on.month - path.start_on.month
        observations = {item.series_id: item.monthly_rate for item in path.months[offset].observations}
        return sum((item.weight * observations[item.series_id] for item in treatment.series), start=ZERO)
