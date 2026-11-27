"""Immutable monthly economic paths and their construction metadata."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from hashlib import sha256

from moneylab import _codec
from moneylab._calendar import month_boundary
from moneylab.domain.values import Revision, distinct_records, identifier

from .rates import CALCULATION_CONTEXT, monthly_effective_rate, validate_annual_effective_rate


class EconomicPathError(ValueError):
    """Economic observations or exposure inputs are unusable for a path run."""


class SeriesKind(str, Enum):
    INVESTMENT_RETURN = "investment_return"
    INFLATION = "inflation"


@dataclass(frozen=True, slots=True)
class EconomicSeries:
    id: str
    kind: SeriesKind

    def __post_init__(self):
        try:
            identifier(self.id)
        except ValueError as exc:
            raise EconomicPathError(str(exc)) from exc
        if not isinstance(self.kind, SeriesKind):
            raise EconomicPathError("expected an economic series kind")


@dataclass(frozen=True, slots=True)
class EconomicObservation:
    series_id: str
    monthly_rate: Decimal

    def __post_init__(self):
        try:
            identifier(self.series_id)
        except ValueError as exc:
            raise EconomicPathError(str(exc)) from exc
        rate = self.monthly_rate
        if not isinstance(rate, Decimal) or not rate.is_finite() or rate < -1:
            raise EconomicPathError("monthly rates must be finite Decimals at least -1")
        # Keep the canonical whole-number envelope but retain conversion precision.
        if rate.as_tuple().exponent < -60 or (rate and rate.adjusted() >= 18):
            raise EconomicPathError("monthly rates support 18 integer and 60 fractional places")


def _unique(records, record_type, *, key):
    try:
        return distinct_records(records, record_type, key=key)
    except (TypeError, ValueError) as exc:
        raise EconomicPathError(str(exc)) from exc


def _check_boundary(value: date) -> None:
    if type(value) is not date or value.day != 1:
        raise EconomicPathError("economic path boundaries must be first-of-month dates")


@dataclass(frozen=True, slots=True)
class EconomicMonth:
    start_on: date
    end_before: date
    observations: tuple[EconomicObservation, ...]

    def __post_init__(self):
        _check_boundary(self.start_on)
        _check_boundary(self.end_before)
        try:
            following = month_boundary(self.start_on, 1)
        except ValueError as exc:
            raise EconomicPathError("economic month extends beyond the calendar range") from exc
        if self.end_before != following:
            raise EconomicPathError("an economic period must cover exactly one calendar month")
        observations = _unique(self.observations, EconomicObservation, key=lambda item: item.series_id)
        object.__setattr__(self, "observations", observations)


@dataclass(frozen=True, slots=True)
class AnnualRate:
    series_id: str
    annual_effective_rate: Decimal

    def __post_init__(self):
        try:
            identifier(self.series_id)
            validate_annual_effective_rate(self.annual_effective_rate)
        except ValueError as exc:
            raise EconomicPathError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PathMetadata:
    methodology: Revision
    source: Revision | None = None
    annual_assumptions: tuple[AnnualRate, ...] = ()
    parameters: Revision | None = None
    seed: int | None = None
    path_index: int | None = None
    random_algorithm: Revision | None = None
    parent_content_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.methodology, Revision):
            raise EconomicPathError("path construction requires a methodology revision")
        for reference in (self.source, self.parameters, self.random_algorithm):
            if reference is not None and not isinstance(reference, Revision):
                raise EconomicPathError("path references must be versioned")
        for name in ("seed", "path_index"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise EconomicPathError(f"{name} must be a nonnegative integer")
        parent = self.parent_content_id
        if parent is not None and (
            not isinstance(parent, str) or len(parent) != 64
            or any(char not in "0123456789abcdef" for char in parent)
        ):
            raise EconomicPathError("parent content ID must be a lowercase SHA-256 digest")
        assumptions = _unique(self.annual_assumptions, AnnualRate, key=lambda item: item.series_id)
        object.__setattr__(self, "annual_assumptions", assumptions)


@dataclass(frozen=True, slots=True)
class EconomicPath:
    series: tuple[EconomicSeries, ...]
    months: tuple[EconomicMonth, ...]
    metadata: PathMetadata
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise EconomicPathError("unsupported economic path schema version")
        if not isinstance(self.metadata, PathMetadata):
            raise EconomicPathError("path requires construction metadata")
        series = _unique(self.series, EconomicSeries, key=lambda item: item.id)
        try:
            months = tuple(self.months)
        except TypeError as exc:
            raise EconomicPathError("path requires economic months") from exc
        if not months or any(not isinstance(month, EconomicMonth) for month in months):
            raise EconomicPathError("path requires at least one economic month")

        ids = tuple(item.id for item in series)
        inflation = [item.id for item in series if item.kind is SeriesKind.INFLATION]
        if len(inflation) > 1:
            raise EconomicPathError("path supports at most one inflation series")
        if not {item.series_id for item in self.metadata.annual_assumptions} <= set(ids):
            raise EconomicPathError("generation assumptions must reference known series")
        previous_end = months[0].start_on
        for month in months:
            if month.start_on != previous_end:
                raise EconomicPathError("path periods must be chronological, unique, and contiguous")
            previous_end = month.end_before
            if tuple(item.series_id for item in month.observations) != ids:
                raise EconomicPathError(f"{month.start_on}: observations must cover the declared series exactly")
            if inflation and any(
                item.series_id == inflation[0] and item.monthly_rate <= -1 for item in month.observations
            ):
                raise EconomicPathError(f"{month.start_on}: monthly inflation must be greater than -1")
        object.__setattr__(self, "series", series)
        object.__setattr__(self, "months", months)

    @property
    def start_on(self) -> date:
        return self.months[0].start_on

    @property
    def end_before(self) -> date:
        return self.months[-1].end_before

    @property
    def horizon_months(self) -> int:
        return len(self.months)

    @property
    def inflation_series_id(self) -> str | None:
        return next((item.id for item in self.series if item.kind is SeriesKind.INFLATION), None)

    def subpath(self, start_on: date, end_before: date) -> "EconomicPath":
        """Select a nonempty calendar slice and retain its parent content identity."""
        _check_boundary(start_on)
        _check_boundary(end_before)
        if not self.start_on <= start_on < end_before <= self.end_before:
            raise EconomicPathError("requested subpath falls outside existing calendar coverage")
        if start_on == self.start_on and end_before == self.end_before:
            return self
        start = (start_on.year - self.start_on.year) * 12 + start_on.month - self.start_on.month
        count = (end_before.year - start_on.year) * 12 + end_before.month - start_on.month
        return replace(self, months=self.months[start:start + count],
                       metadata=replace(self.metadata, parent_content_id=self.content_id))

    def to_json(self) -> str:
        return _codec.dumps(self)

    @classmethod
    def from_json(cls, payload: str) -> "EconomicPath":
        try:
            return _codec.loads(payload, cls)
        except EconomicPathError:
            raise
        except (TypeError, ValueError) as exc:
            raise EconomicPathError(str(exc)) from exc

    @property
    def content_id(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()


CONSTANT_PATH_METHOD = Revision("constant-effective-annual-economic-path", "1.0.0")


def constant_path(
    start_on: date, horizon_months: int, series: Iterable[EconomicSeries],
    annual_assumptions: Iterable[AnnualRate], *, source: Revision | None = None,
) -> EconomicPath:
    """Construct constant realized months from explicit annual effective inputs."""
    _check_boundary(start_on)
    if type(horizon_months) is not int or horizon_months < 1:
        raise EconomicPathError("a constant path requires a positive whole-month horizon")
    try:
        month_boundary(start_on, horizon_months)
    except (ValueError, OverflowError) as exc:
        raise EconomicPathError("path horizon extends beyond the calendar range") from exc
    series = _unique(series, EconomicSeries, key=lambda item: item.id)
    metadata = PathMetadata(CONSTANT_PATH_METHOD, source, annual_assumptions)
    if tuple(item.series_id for item in metadata.annual_assumptions) != tuple(item.id for item in series):
        raise EconomicPathError("constant path assumptions must cover the declared series exactly")
    with localcontext(CALCULATION_CONTEXT):
        observations = tuple(
            EconomicObservation(item.series_id, monthly_effective_rate(item.annual_effective_rate))
            for item in metadata.annual_assumptions
        )
    months = tuple(EconomicMonth(month_boundary(start_on, offset), month_boundary(start_on, offset + 1),
                                 observations) for offset in range(horizon_months))
    return EconomicPath(series, months, metadata)
