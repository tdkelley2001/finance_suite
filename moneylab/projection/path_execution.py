"""Map shared realized observations to the existing monthly financial executor."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from hashlib import sha256

from moneylab import _codec
from moneylab.configuration.models import PositionGrowth
from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.profile import Liability
from moneylab.domain.values import Revision, distinct_records, identifier
from moneylab.economics import EconomicPath, EconomicPathError, SeriesKind
from moneylab.economics.rates import (
    CALCULATION_CONTEXT, ONE, monthly_effective_rate, validate_annual_effective_rate,
)

from .engine import _run_months
from .readiness import METHODOLOGY, PATH_METHODOLOGY, prepare
from .results import ProjectionResult


@dataclass(frozen=True, slots=True)
class PositionExposure:
    position_id: str
    series_id: str | None = None
    annual_effective_rate: Decimal | None = None

    def __post_init__(self):
        if (self.series_id is None) == (self.annual_effective_rate is None):
            raise EconomicPathError("a position needs exactly one series or explicit effective annual rate")
        try:
            identifier(self.position_id)
            if self.series_id is not None:
                identifier(self.series_id)
            else:
                validate_annual_effective_rate(self.annual_effective_rate)
        except ValueError as exc:
            raise EconomicPathError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class PathExecutionReference:
    input_content_id: str
    input_schema_version: int
    path_content_id: str
    path_schema_version: int
    path_methodology: Revision
    exposures: tuple[PositionExposure, ...]
    execution_methodology: Revision = PATH_METHODOLOGY
    financial_methodology: Revision = METHODOLOGY
    schema_version: int = 1

    @property
    def content_id(self) -> str:
        return sha256(_codec.dumps(self).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PathProjectionResult:
    projection: ProjectionResult
    execution: PathExecutionReference
    schema_version: int = 1

    @property
    def execution_content_id(self) -> str:
        return self.execution.content_id

    def to_json(self) -> str:
        return _codec.dumps(self)


def _validate_economics(snapshot, positions, path, exposures):
    if not isinstance(path, EconomicPath):
        raise EconomicPathError("expected an economic path")
    if (path.start_on != snapshot.request.inputs.start_on
            or path.horizon_months != snapshot.preferences.horizon_months):
        raise EconomicPathError("path must match the projection's start and horizon exactly; select a subpath")
    if snapshot.assumptions.annual_inflation is not None:
        raise EconomicPathError("path execution requires annual inflation to be unset in the financial snapshot")
    if snapshot.preferences.use_real_dollars and path.inflation_series_id is None:
        raise EconomicPathError("real-dollar path execution requires complete monthly inflation")

    try:
        exposures = distinct_records(exposures, PositionExposure, key=lambda item: item.position_id)
    except (TypeError, ValueError) as exc:
        raise EconomicPathError(str(exc)) from exc
    expected = {key for key, position in positions.items() if not isinstance(position, Liability)}
    kinds = {series.id: series.kind for series in path.series}
    deterministic = {item.position_id: item.annual_effective_rate for item in snapshot.position_growth}
    for exposure in exposures:
        key = exposure.position_id
        if key not in expected:
            raise EconomicPathError(f"{key}: growth exposure requires an in-scope account or asset")
        if exposure.series_id is not None and kinds.get(exposure.series_id) is not SeriesKind.INVESTMENT_RETURN:
            raise EconomicPathError(f"{key}: exposure requires a known investment return series")
        if key in deterministic and exposure.annual_effective_rate != deterministic[key]:
            raise EconomicPathError(f"{key}: exposure conflicts with the snapshot's deterministic growth")
    missing = expected - {item.position_id for item in exposures}
    if missing:
        raise EconomicPathError(f"missing growth exposures for {', '.join(sorted(missing))}")
    return exposures


def _conditions(path, exposures, constant_rates, inflation_series):
    for month in path.months:
        observed = {item.series_id: item.monthly_rate for item in month.observations}
        rates = {
            entry.position_id: (
                observed[entry.series_id] if entry.series_id is not None else constant_rates[entry.position_id]
            )
            for entry in exposures
        }
        inflation_factor = None if inflation_series is None else ONE + observed[inflation_series]
        yield rates, inflation_factor


def project_economic_path(
    snapshot: ResolvedAnalysis, path: EconomicPath, exposures: Iterable[PositionExposure],
) -> PathProjectionResult:
    """Execute one validated, fully realized path using M03 financial settlement."""
    prepared = prepare(snapshot, path_driven=True)
    exposures = _validate_economics(snapshot, prepared.positions, path, exposures)
    deterministic_growth = tuple(
        PositionGrowth(entry.position_id, entry.annual_effective_rate)
        for entry in exposures if entry.annual_effective_rate is not None
    )
    inflation_series = path.inflation_series_id
    with localcontext(CALCULATION_CONTEXT):
        rates = {
            item.position_id: monthly_effective_rate(item.annual_effective_rate)
            for item in deterministic_growth
        }
        projection = _run_months(
            snapshot, prepared, _conditions(path, exposures, rates, inflation_series),
            methodology=PATH_METHODOLOGY, has_inflation=inflation_series is not None, annual_inflation=None,
            position_growth=deterministic_growth,
        )
    reference = PathExecutionReference(
        input_content_id=projection.input_content_id, input_schema_version=snapshot.schema_version,
        path_content_id=path.content_id, path_schema_version=path.schema_version,
        path_methodology=path.metadata.methodology, exposures=exposures,
    )
    return PathProjectionResult(projection, reference)
