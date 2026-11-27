"""Immutable, versioned inputs for a single analysis."""

from dataclasses import dataclass, fields
from hashlib import sha256

from moneylab.domain.planning import FinancialPlan
from moneylab.domain.profile import FinancialProfile, Liability
from moneylab.domain.values import Revision, Source, distinct_records, identifier

from . import _codec
from .models import AnalysisRequest, AnalysisType, EconomicAssumptions, ModelPreferences


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
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
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

        expected_origins = {"analysis.inputs"}
        for section in ("assumptions", "preferences"):
            record = getattr(self, section)
            expected_origins.update(
                f"{section}.{field.name}" for field in fields(record)
                if getattr(record, field.name) is not None
            )

        if self.request.analysis_type is AnalysisType.LOAN_PAYMENT:
            if (self.profile is not None or self.plan is not None
                    or any(ref is not None for ref in revisions)
                    or expected_origins != {"analysis.inputs"}):
                raise ValueError("loan snapshot accepts only explicit standalone inputs")
        else:
            self._validate_projection()
            expected_origins.add("profile")
            if self.plan is not None:
                expected_origins.add("plan")
                expected_origins.update(
                    activity_amount_field(activity.id) for activity in self.plan.activities
                )
        if expected_origins != {origin.field for origin in origins}:
            raise ValueError("snapshot origins must cover the resolved inputs")

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
        for position in self.profile.positions_for(inputs.subject):
            valuation = position.balance if isinstance(position, Liability) else position.valuation
            if valuation.amount is None:
                raise MissingAnalysisInput(f"projection requires an opening amount for {position.id}")
            if valuation.as_of > inputs.start_on:
                raise ValueError(f"{position.id} valuation is dated after the projection start")

    def to_json(self) -> str:
        """Return canonical JSON for the complete recorded input snapshot."""
        return _codec.dumps(self)

    @classmethod
    def from_json(cls, payload: str) -> "ResolvedAnalysis":
        return _codec.loads(payload, cls)

    @property
    def content_id(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()
