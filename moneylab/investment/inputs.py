"""Immutable, versioned investment inputs bound to a financial snapshot."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from hashlib import sha256

from moneylab import _codec
from moneylab.domain.values import (
    Revision, Source, Valuation, calendar_date, decimal_sum, decimal_value, distinct_records, identifier,
)
from moneylab.economics.rates import CALCULATION_CONTEXT

from .allocation import ZERO, fraction
from .exposures import CostKind, ReturnTreatment, annual_fee
from .models import Investment, InvestmentMode, Sleeve
from .policy import ContributionKind, InvestmentPolicy
from .taxonomy import ExposureCategory, ExposureTaxonomy


class OpeningBasis(str, Enum):
    REPORTED = "reported"
    HYPOTHETICAL = "hypothetical"
    UNCLASSIFIED = "unclassified"
    FUTURE_DESTINATION = "future_destination"


@dataclass(frozen=True, slots=True)
class ResolvedSleeve:
    sleeve: Sleeve
    amount: Decimal
    basis: OpeningBasis
    disclosed_weight: Decimal | None = None

    def __post_init__(self):
        if not isinstance(self.sleeve, Sleeve) or not isinstance(self.basis, OpeningBasis):
            raise ValueError("resolved sleeve requires a model and opening basis")
        decimal_value(self.amount, minimum=0)
        if self.disclosed_weight is not None:
            fraction(self.disclosed_weight)
        if self.basis is OpeningBasis.FUTURE_DESTINATION and (self.amount or self.sleeve.holding_id is not None):
            raise ValueError("future destinations must start empty and without a holding")
        if self.basis is OpeningBasis.REPORTED and self.sleeve.holding_id is None:
            raise ValueError("reported sleeves require a holding reference")
        if self.basis is OpeningBasis.HYPOTHETICAL and self.disclosed_weight is None:
            raise ValueError("hypothetical sleeves require an explicit opening weight")
        if self.basis is OpeningBasis.UNCLASSIFIED and (
            self.sleeve.holding_id is not None or self.disclosed_weight is not None
        ):
            raise ValueError("unclassified residual cannot replace a reported holding or weight")

    @property
    def id(self) -> str:
        return self.sleeve.id


@dataclass(frozen=True, slots=True)
class ResolvedInvestment:
    investment: Investment
    return_source: Source

    def __post_init__(self):
        if (not isinstance(self.investment, Investment) or self.investment.treatment is None
                or not isinstance(self.return_source, Source)):
            raise ValueError("resolved investment requires an effective return and source")
        self.investment.treatment.convention.require_separate(
            CostKind.FUND_EXPENSE, self.investment.annual_fund_expense,
        )

    @property
    def id(self) -> str:
        return self.investment.id


@dataclass(frozen=True, slots=True)
class ResolvedAccount:
    account_id: str
    opening: Valuation
    valuation_source: Source
    mode: InvestmentMode
    sleeves: tuple[ResolvedSleeve, ...] = ()
    unclassified_opening: Decimal = ZERO
    allocation_source: Source | None = None
    aggregate_return: ReturnTreatment | None = None
    aggregate_return_source: Source | None = None
    annual_advisory_fee: Decimal | None = None
    policy: InvestmentPolicy | None = None
    policy_source: Source | None = None

    def __post_init__(self):
        identifier(self.account_id)
        if not isinstance(self.opening, Valuation) or self.opening.amount is None:
            raise ValueError("investment inputs require a known opening valuation")
        if not isinstance(self.mode, InvestmentMode) or not isinstance(self.valuation_source, Source):
            raise ValueError("account investments require a mode and valuation source")
        annual_fee(self.annual_advisory_fee)
        decimal_value(self.unclassified_opening, minimum=0)
        sleeves = distinct_records(self.sleeves, ResolvedSleeve)
        object.__setattr__(self, "sleeves", sleeves)
        if self.mode is InvestmentMode.AGGREGATE:
            if (sleeves or self.policy is not None or self.policy_source is not None
                    or self.allocation_source is not None or self.unclassified_opening != self.opening.amount
                    or not isinstance(self.aggregate_return, ReturnTreatment)
                    or not isinstance(self.aggregate_return_source, Source)):
                raise ValueError("aggregate investments must cover the entire account without sleeve inputs")
            return
        if self.aggregate_return is not None or self.aggregate_return_source is not None:
            raise ValueError("detailed investments cannot include an aggregate return")
        if not sleeves or not isinstance(self.allocation_source, Source):
            raise ValueError("detailed investments require sleeves and an allocation source")
        if (self.policy is None) != (self.policy_source is None) or (
            self.policy is not None
            and (not isinstance(self.policy, InvestmentPolicy) or not isinstance(self.policy_source, Source))
        ):
            raise ValueError("effective policy and its source must be supplied together")
        if decimal_sum([self.unclassified_opening, *(item.amount for item in sleeves)]) != self.opening.amount:
            raise ValueError(f"{self.account_id} sleeve amounts do not reconcile to the opening valuation")
        links = [item.sleeve.holding_id for item in sleeves if item.sleeve.holding_id is not None]
        if len(links) != len(set(links)):
            raise ValueError("resolved holding references must be unique within the account")
        hypothetical = [item for item in sleeves if item.basis is OpeningBasis.HYPOTHETICAL]
        if hypothetical and (len(hypothetical) != len(sleeves)
                             or decimal_sum(item.disclosed_weight for item in hypothetical) != 1
                             or self.unclassified_opening):
            raise ValueError("hypothetical composition must replace the entire opening allocation")

    def current_weights(self) -> dict[str, Decimal] | None:
        """Derive modeled sleeve weights from actual resolved money, before any policy."""
        if self.mode is InvestmentMode.AGGREGATE or not self.opening.amount:
            return None
        with localcontext(CALCULATION_CONTEXT):
            return {item.id: item.amount / self.opening.amount for item in self.sleeves}


@dataclass(frozen=True, slots=True)
class InvestmentReadinessIssue:
    code: str
    account_id: str


class InvestmentReadinessError(ValueError):
    def __init__(self, issues: tuple[InvestmentReadinessIssue, ...]):
        self.issues = issues
        super().__init__(" | ".join(f"{item.account_id}: {item.code}" for item in issues))


def _content_reference(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("expected a lowercase SHA-256 content reference")


@dataclass(frozen=True, slots=True)
class ResolvedInvestmentInputs:
    snapshot_content_id: str
    snapshot_schema_version: int
    plan_revision: Revision
    taxonomy: ExposureTaxonomy
    currency: str
    start_on: date
    accounts: tuple[ResolvedAccount, ...]
    investments: tuple[ResolvedInvestment, ...]
    economic_path_content_id: str | None = None
    economic_path_schema_version: int | None = None
    scenario_revision: Revision | None = None
    preset_revision: Revision | None = None
    defaults_revision: Revision | None = None
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported investment input schema")
        if type(self.snapshot_schema_version) is not int or self.snapshot_schema_version < 1:
            raise ValueError("expected a financial snapshot schema version")
        if not isinstance(self.plan_revision, Revision) or not isinstance(self.taxonomy, ExposureTaxonomy):
            raise ValueError("expected investment plan and taxonomy revisions")
        calendar_date(self.start_on)
        if self.start_on.day != 1:
            raise ValueError("investment inputs require a first-of-month opening")
        for revision in (self.scenario_revision, self.preset_revision, self.defaults_revision):
            if revision is not None and not isinstance(revision, Revision):
                raise ValueError("expected a versioned investment configuration reference")
        _content_reference(self.snapshot_content_id)
        if (self.economic_path_content_id is None) != (self.economic_path_schema_version is None):
            raise ValueError("economic path identity and schema version must be supplied together")
        if self.economic_path_content_id is not None:
            _content_reference(self.economic_path_content_id)
            if type(self.economic_path_schema_version) is not int or self.economic_path_schema_version < 1:
                raise ValueError("expected an economic path schema version")
        accounts = distinct_records(self.accounts, ResolvedAccount, key=lambda item: item.account_id)
        investments = distinct_records(self.investments, ResolvedInvestment)
        object.__setattr__(self, "accounts", accounts)
        object.__setattr__(self, "investments", investments)
        if not accounts or any(account.opening.currency != self.currency for account in accounts):
            raise ValueError("resolved investments require accounts in one projection currency")
        if any(account.opening.as_of > self.start_on for account in accounts):
            raise ValueError("opening valuations cannot be dated after investment analysis starts")
        self._validate_treatments()

    def _validate_treatments(self):
        by_id = {item.id: item.investment.treatment for item in self.investments}
        used = {sleeve.sleeve.investment_id for account in self.accounts for sleeve in account.sleeves}
        if used != by_id.keys():
            raise ValueError("resolved sleeves must match the effective investment catalog")
        series_conventions = {}
        for account in self.accounts:
            treatments = {sleeve.id: by_id[sleeve.sleeve.investment_id] for sleeve in account.sleeves}
            used_returns = treatments.values() if treatments else (account.aggregate_return,)
            for treatment in used_returns:
                treatment.validate_convention(self.currency, self.taxonomy)
                treatment.convention.require_separate(CostKind.ADVISORY_FEE, account.annual_advisory_fee)
                for link in treatment.series:
                    if self.economic_path_content_id is None:
                        raise ValueError("series exposure requires the selected economic path identity")
                    existing = series_conventions.setdefault(link.series_id, treatment.convention)
                    if existing != treatment.convention:
                        raise ValueError(f"conflicting return conventions for series {link.series_id}")
            if account.policy is not None:
                cash = {
                    key for key, treatment in treatments.items()
                    if all(exposure is not None and self.taxonomy.require(exposure).category is ExposureCategory.CASH
                           for exposure in treatment.exposure_weights())
                }
                account.policy.validate_destinations(set(treatments), cash)

    def readiness_issues(self) -> tuple[InvestmentReadinessIssue, ...]:
        """Report known opening blockers without promising future execution eligibility."""
        issues = []
        for account in self.accounts:
            if account.opening.as_of != self.start_on:
                issues.append(InvestmentReadinessIssue("unaligned_opening_valuation", account.account_id))
            if account.mode is InvestmentMode.DETAILED and account.unclassified_opening:
                issues.append(InvestmentReadinessIssue("unclassified_opening_value", account.account_id))
            policy = account.policy.contribution if account.policy is not None else None
            if (not account.opening.amount and policy is not None and policy.kind is ContributionKind.CURRENT
                    and policy.zero_balance_fallback is None):
                issues.append(InvestmentReadinessIssue("missing_zero_balance_fallback", account.account_id))
        return tuple(issues)

    def require_ready(self) -> None:
        issues = self.readiness_issues()
        if issues:
            raise InvestmentReadinessError(issues)

    def to_json(self) -> str:
        return _codec.dumps(self)

    @classmethod
    def from_json(cls, payload: str) -> "ResolvedInvestmentInputs":
        return _codec.loads(payload, cls)

    @property
    def content_id(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()
