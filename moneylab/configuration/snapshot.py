"""Immutable, versioned inputs for a single analysis."""

from dataclasses import dataclass, fields, replace
from datetime import date
from hashlib import sha256

from moneylab.domain.planning import FinancialPlan
from moneylab.domain.profile import Account, Asset, FinancialProfile, Liability
from moneylab.domain.values import Revision, Source, SourceKind, Valuation, distinct_records, identifier

from . import _codec
from .models import (
    AnalysisRequest, AnalysisType, EconomicAssumptions, ModelPreferences, PositionValuationOverride,
)


class MissingAnalysisInput(ValueError):
    """A valid record set lacks an input required by the selected analysis."""


@dataclass(frozen=True, slots=True)
class InputOrigin:
    field: str
    source: Source

    def __post_init__(self):
        identifier(self.field)
        if not isinstance(self.source, Source):
            raise ValueError("expected an input source")


def activity_amount_field(activity_id: str) -> str:
    return f"plan.activities.{activity_id}.amount"


def position_valuation_field(position_id: str) -> str:
    return f"opening.positions.{position_id}.valuation"


def _valuation(position: Account | Asset | Liability) -> Valuation:
    return position.balance if isinstance(position, Liability) else position.valuation


def validate_position_override(
    override: PositionValuationOverride,
    positions: dict[str, Account | Asset | Liability],
    start_on: date,
) -> None:
    position = positions.get(override.position_id)
    if position is None:
        raise ValueError(f"{override.position_id} is an unknown or out-of-scope position")
    valuation = override.valuation
    baseline = _valuation(position)
    if valuation.currency != baseline.currency:
        raise ValueError(f"{position.id} override requires {baseline.currency}, got {valuation.currency}")
    if valuation.as_of > start_on:
        raise ValueError(f"{position.id} override valuation is dated after the projection start")
    if isinstance(position, Account):
        if valuation.as_of != baseline.as_of and any(h.value is not None for h in position.holdings):
            raise ValueError(f"{position.id} with valued holdings requires the original valuation date")
        # Reuse the account invariant that disclosed holdings fit within its valuation.
        replace(position, valuation=valuation)


@dataclass(frozen=True, slots=True)
class ResolvedAnalysis:
    request: AnalysisRequest
    profile: FinancialProfile | None = None
    plan: FinancialPlan | None = None
    assumptions: EconomicAssumptions = EconomicAssumptions()
    preferences: ModelPreferences = ModelPreferences()
    scenario_revision: Revision | None = None
    preset_revision: Revision | None = None
    defaults_revision: Revision | None = None
    origins: tuple[InputOrigin, ...] = ()
    position_valuations: tuple[PositionValuationOverride, ...] = ()
    schema_version: int = 2

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ValueError("unsupported analysis snapshot schema version")
        if (not isinstance(self.request, AnalysisRequest)
                or not isinstance(self.assumptions, EconomicAssumptions)
                or not isinstance(self.preferences, ModelPreferences)):
            raise ValueError("expected a typed request, assumptions and preferences")
        revisions = (self.scenario_revision, self.preset_revision, self.defaults_revision)
        if any(ref is not None and not isinstance(ref, Revision) for ref in revisions):
            raise ValueError("expected versioned scenario, preset and default references")
        origins = distinct_records(self.origins, InputOrigin, key=lambda origin: origin.field)
        object.__setattr__(self, "origins", origins)
        valuations = distinct_records(
            self.position_valuations, PositionValuationOverride, key=lambda entry: entry.position_id,
        )
        object.__setattr__(self, "position_valuations", valuations)

        expected_origins = {"analysis.inputs"}
        for section in ("assumptions", "preferences"):
            record = getattr(self, section)
            expected_origins.update(
                f"{section}.{field.name}" for field in fields(record)
                if getattr(record, field.name) is not None
            )

        if self.request.analysis_type is AnalysisType.LOAN_PAYMENT:
            if (self.profile is not None or self.plan is not None
                    or self.position_valuations
                    or any(ref is not None for ref in revisions)
                    or expected_origins != {"analysis.inputs"}):
                raise ValueError("loan snapshot accepts only explicit standalone inputs")
        else:
            self._validate_projection()
            expected_origins.add("profile")
            expected_origins.update(position_valuation_field(entry.position_id) for entry in valuations)
            if self.plan is not None:
                expected_origins.add("plan")
                expected_origins.update(
                    activity_amount_field(activity.id) for activity in self.plan.activities
                )
        if expected_origins != {origin.field for origin in origins}:
            raise ValueError("snapshot origins must cover the resolved inputs")

        sources = {origin.field: origin.source for origin in origins}
        for entry in valuations:
            source = sources[position_valuation_field(entry.position_id)]
            if source.kind is SourceKind.LOCAL_OVERRIDE:
                continue
            if (source.kind is not SourceKind.SCENARIO_OVERRIDE or self.scenario_revision is None
                    or source.reference != self.scenario_revision):
                raise ValueError("opening position overrides require local or matching scenario provenance")

    def _validate_projection(self):
        if self.profile is None:
            raise MissingAnalysisInput("projection requires a financial profile")
        if not isinstance(self.profile, FinancialProfile):
            raise ValueError("expected a financial profile")
        if self.preferences.horizon_months is None:
            raise MissingAnalysisInput("projection requires a horizon in months")
        if self.preferences.use_real_dollars and self.assumptions.annual_inflation is None:
            raise MissingAnalysisInput("real-dollar projection requires an inflation assumption")
        if self.plan is not None:
            if not isinstance(self.plan, FinancialPlan):
                raise ValueError("expected a financial plan")
            self.plan.validate_against(self.profile)
        inputs = self.request.inputs
        positions = {position.id: position for position in self.profile.positions_for(inputs.subject)}
        effective = {position_id: _valuation(position) for position_id, position in positions.items()}
        for override in self.position_valuations:
            validate_position_override(override, positions, inputs.start_on)
            effective[override.position_id] = override.valuation
        for position_id, valuation in effective.items():
            if valuation.amount is None:
                raise MissingAnalysisInput(f"projection requires an opening amount for {position_id}")
            if valuation.as_of > inputs.start_on:
                raise ValueError(f"{position_id} valuation is dated after the projection start")

    def opening_valuations(self) -> dict[str, Valuation]:
        """Return the scoped effective valuations, leaving the recorded profile intact."""
        if self.profile is None:
            return {}
        values = {
            position.id: _valuation(position)
            for position in self.profile.positions_for(self.request.inputs.subject)
        }
        values.update((entry.position_id, entry.valuation) for entry in self.position_valuations)
        return values

    def to_json(self) -> str:
        """Return canonical JSON for the complete recorded input snapshot."""
        return _codec.dumps(self)

    @classmethod
    def from_json(cls, payload: str) -> "ResolvedAnalysis":
        return _codec.loads(payload, cls)

    @property
    def content_id(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()
