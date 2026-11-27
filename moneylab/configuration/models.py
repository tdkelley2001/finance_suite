"""Explicit configuration inputs with closed sets of eligible fields."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from moneylab.domain.planning import nonnegative_money
from moneylab.domain.profile import Subject
from moneylab.domain.values import (
    Money,
    Revision,
    Valuation,
    calendar_date,
    decimal_value,
    distinct_records,
    identifier,
    integer,
)


@dataclass(frozen=True, slots=True)
class EconomicAssumptions:
    annual_inflation: Decimal | None = None
    annual_investment_return: Decimal | None = None

    def __post_init__(self):
        for value in (self.annual_inflation, self.annual_investment_return):
            if value is not None:
                decimal_value(value)
                if value <= -1:
                    raise ValueError("annual economic rates must be greater than -1")


@dataclass(frozen=True, slots=True)
class ModelPreferences:
    horizon_months: int | None = None
    use_real_dollars: bool | None = None

    def __post_init__(self):
        if self.horizon_months is not None:
            integer(self.horizon_months, minimum=1)
        if self.use_real_dollars is not None and type(self.use_real_dollars) is not bool:
            raise ValueError("use_real_dollars must be boolean")


def _validate_sections(assumptions, preferences):
    if not isinstance(assumptions, EconomicAssumptions) or not isinstance(preferences, ModelPreferences):
        raise ValueError("configuration requires typed assumptions and model preferences")


@dataclass(frozen=True, slots=True)
class Preset:
    revision: Revision
    name: str
    assumptions: EconomicAssumptions = EconomicAssumptions()
    preferences: ModelPreferences = ModelPreferences()

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("expected a preset revision")
        identifier(self.name)
        _validate_sections(self.assumptions, self.preferences)


@dataclass(frozen=True, slots=True)
class ResearchDefaults:
    revision: Revision
    assumptions: EconomicAssumptions = EconomicAssumptions()
    preferences: ModelPreferences = ModelPreferences()

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("expected a research defaults revision")
        _validate_sections(self.assumptions, self.preferences)


@dataclass(frozen=True, slots=True)
class ActivityAmountOverride:
    activity_id: str
    amount: Money

    def __post_init__(self):
        identifier(self.activity_id)
        nonnegative_money(self.amount)


@dataclass(frozen=True, slots=True)
class PositionValuationOverride:
    position_id: str
    valuation: Valuation

    def __post_init__(self):
        identifier(self.position_id)
        if not isinstance(self.valuation, Valuation) or self.valuation.amount is None:
            raise ValueError("a position override requires an explicit dated amount")


@dataclass(frozen=True, slots=True)
class AnalysisOverrides:
    assumptions: EconomicAssumptions = EconomicAssumptions()
    preferences: ModelPreferences = ModelPreferences()
    activity_amounts: tuple[ActivityAmountOverride, ...] = ()
    position_valuations: tuple[PositionValuationOverride, ...] = ()

    def __post_init__(self):
        _validate_sections(self.assumptions, self.preferences)
        amounts = distinct_records(
            self.activity_amounts, ActivityAmountOverride, key=lambda entry: entry.activity_id,
        )
        object.__setattr__(self, "activity_amounts", amounts)
        valuations = distinct_records(
            self.position_valuations, PositionValuationOverride, key=lambda entry: entry.position_id,
        )
        object.__setattr__(self, "position_valuations", valuations)


@dataclass(frozen=True, slots=True)
class Scenario:
    revision: Revision
    name: str
    profile_id: str
    plan_id: str | None = None
    preset_id: str | None = None
    overrides: AnalysisOverrides = AnalysisOverrides()

    def __post_init__(self):
        if not isinstance(self.revision, Revision) or not isinstance(self.overrides, AnalysisOverrides):
            raise ValueError("scenario requires a revision and typed overrides")
        for name in (self.name, self.profile_id):
            identifier(name)
        for reference in (self.plan_id, self.preset_id):
            if reference is not None:
                identifier(reference)


class AnalysisType(str, Enum):
    LOAN_PAYMENT = "loan_payment"
    MONTHLY_PROJECTION = "monthly_projection"


@dataclass(frozen=True, slots=True)
class LoanPaymentInputs:
    principal: Money
    annual_rate: Decimal
    term_months: int

    def __post_init__(self):
        nonnegative_money(self.principal)
        decimal_value(self.annual_rate, minimum=0)
        integer(self.term_months, minimum=1)


@dataclass(frozen=True, slots=True)
class MonthlyProjectionInputs:
    subject: Subject
    start_on: date

    def __post_init__(self):
        if not isinstance(self.subject, Subject):
            raise ValueError("expected a projection subject")
        calendar_date(self.start_on)
        if self.start_on.day != 1:
            raise ValueError("projection start must be the first day of a month")


@dataclass(frozen=True, slots=True)
class StochasticExecution:
    seed: int
    path_count: int

    def __post_init__(self):
        integer(self.seed, minimum=0)
        integer(self.path_count, minimum=1)


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    analysis_type: AnalysisType
    inputs: LoanPaymentInputs | MonthlyProjectionInputs
    methodology: Revision | None = None
    external_data: tuple[Revision, ...] = ()
    stochastic: StochasticExecution | None = None

    def __post_init__(self):
        if self.analysis_type is AnalysisType.LOAN_PAYMENT:
            if not isinstance(self.inputs, LoanPaymentInputs) or self.stochastic is not None:
                raise ValueError("loan payment requires standalone loan inputs")
        elif self.analysis_type is AnalysisType.MONTHLY_PROJECTION:
            if not isinstance(self.inputs, MonthlyProjectionInputs):
                raise ValueError("projection requires a start date and subject")
        else:
            raise ValueError("unsupported analysis type")
        if self.methodology is not None and not isinstance(self.methodology, Revision):
            raise ValueError("expected a methodology revision")
        if self.stochastic is not None and not isinstance(self.stochastic, StochasticExecution):
            raise ValueError("expected stochastic execution settings")
        object.__setattr__(self, "external_data", distinct_records(self.external_data, Revision))
