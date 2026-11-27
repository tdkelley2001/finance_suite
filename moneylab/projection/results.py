"""Structured observations, financial postings and termination diagnostics."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from moneylab import _codec
from moneylab.configuration.models import PositionGrowth
from moneylab.domain.profile import Subject
from moneylab.domain.values import Revision


class PositionKind(str, Enum):
    ACCOUNT = "account"
    ASSET = "asset"
    LIABILITY = "liability"


class EffectKind(str, Enum):
    INCOME = "external_income"
    EXPENSE = "external_expense"
    TRANSFER = "transfer"
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"
    ACCOUNT_RETURN = "account_return"
    ASSET_REVALUATION = "asset_revaluation"
    INTEREST_ACCRUED = "debt_interest_accrued"
    INTEREST_PAID = "debt_interest_paid"
    PRINCIPAL_PAID = "debt_principal_paid"


class ProjectionStatus(str, Enum):
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    start_on: date
    end_before: date


@dataclass(frozen=True, slots=True)
class PositionBalance:
    position_id: str
    kind: PositionKind
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Observation:
    as_of: date
    positions: tuple[PositionBalance, ...]
    net_worth: Decimal
    inflation_index: Decimal | None
    real_net_worth: Decimal | None


@dataclass(frozen=True, slots=True)
class Posting:
    position_id: str
    change: Decimal


@dataclass(frozen=True, slots=True)
class FinancialEffect:
    kind: EffectKind
    amount: Decimal
    postings: tuple[Posting, ...]
    activity_id: str | None = None


@dataclass(frozen=True, slots=True)
class Reconciliation:
    max_absolute_position_residual: Decimal
    net_worth_residual: Decimal
    economic_change: Decimal


@dataclass(frozen=True, slots=True)
class MonthResult:
    period: MonthPeriod
    closing: Observation
    effects: tuple[FinancialEffect, ...]
    reconciliation: Reconciliation


@dataclass(frozen=True, slots=True)
class ExecutionIssue:
    code: str
    message: str
    record_id: str | None = None
    amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PlannedAmount:
    activity_id: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class FundingShortfall:
    account_id: str
    available: Decimal
    required: Decimal
    unfunded: Decimal
    debits: tuple[PlannedAmount, ...]


@dataclass(frozen=True, slots=True)
class Termination:
    period: MonthPeriod
    planned: tuple[PlannedAmount, ...]
    issues: tuple[ExecutionIssue, ...] = ()
    shortfalls: tuple[FundingShortfall, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    input_content_id: str
    methodology: Revision
    currency: str
    subject: Subject
    requested_months: int
    completed_months: int
    status: ProjectionStatus
    opening: Observation
    months: tuple[MonthResult, ...]
    annual_inflation: Decimal | None
    position_growth: tuple[PositionGrowth, ...]
    termination: Termination | None = None
    schema_version: int = 1

    def to_json(self) -> str:
        """Encode the modeled observations and their explicit financial effects."""
        return _codec.dumps(self)
