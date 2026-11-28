"""Derived analytical views of existing accounts."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from moneylab.configuration.models import AnalysisType
from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.profile import FinancialProfile, Subject
from moneylab.domain.values import (
    Revision, Source, SourceKind, decimal_sum, distinct_ids, identifier, validate_source,
)
from moneylab.economics.rates import CALCULATION_CONTEXT

from .allocation import apportion
from .inputs import OpeningBasis, ResolvedInvestmentInputs
from .models import InvestmentMode
from .resolve import scoped_accounts


@dataclass(frozen=True, slots=True)
class PortfolioGroup:
    revision: Revision
    name: str
    account_ids: tuple[str, ...]
    source: Source | None = None

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("portfolio group requires a revision")
        identifier(self.name)
        validate_source(self.source, SourceKind.USER_PLAN)
        accounts = distinct_ids(self.account_ids)
        if not accounts:
            raise ValueError("portfolio group requires at least one account")
        object.__setattr__(self, "account_ids", accounts)


@dataclass(frozen=True, slots=True)
class ExposureValue:
    exposure_id: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    group: PortfolioGroup
    currency: str
    total: Decimal | None
    known_total: Decimal
    exposures: tuple[ExposureValue, ...]
    unclassified_value: Decimal
    unknown_value_accounts: tuple[str, ...]
    hypothetical_accounts: tuple[str, ...]

    def exposure_weights(self) -> dict[str | None, Decimal] | None:
        if not self.total:
            return None
        with localcontext(CALCULATION_CONTEXT):
            weights = {item.exposure_id: item.amount / self.total for item in self.exposures}
            weights[None] = self.unclassified_value / self.total
            return weights


def summarize_portfolio(
    group: PortfolioGroup, financial: FinancialProfile | ResolvedAnalysis, *,
    subject: Subject | None = None, investments: ResolvedInvestmentInputs | None = None,
) -> PortfolioSummary:
    """Summarize each named account once using only disclosed modeled exposures."""
    if not isinstance(group, PortfolioGroup):
        raise ValueError("expected a portfolio group")
    if isinstance(financial, ResolvedAnalysis):
        if financial.request.analysis_type is not AnalysisType.MONTHLY_PROJECTION or subject is not None:
            raise ValueError("use the monthly snapshot's existing analysis subject")
        profile, subject = financial.profile, financial.request.inputs.subject
        effective = financial.opening_valuations()
        hypothetical_valuations = {item.position_id for item in financial.position_valuations}
    else:
        if not isinstance(financial, FinancialProfile) or not isinstance(subject, Subject):
            raise ValueError("a financial profile requires an explicit portfolio subject")
        profile = financial
        effective = {item.id: item.valuation for item in profile.accounts}
        hypothetical_valuations = set()

    scoped = scoped_accounts(profile, subject)
    if not set(group.account_ids) <= scoped.keys():
        raise ValueError("portfolio groups require existing in-scope, fully covered accounts")
    if investments is not None and (
        not isinstance(investments, ResolvedInvestmentInputs) or not isinstance(financial, ResolvedAnalysis)
        or investments.snapshot_content_id != financial.content_id
    ):
        raise ValueError("investment allocations must match the financial snapshot")

    models = {} if investments is None else {item.id: item.investment.treatment for item in investments.investments}
    allocations = {} if investments is None else {item.account_id: item for item in investments.accounts}
    unknown, hypothetical = [], []
    known = []
    by_exposure = {None: []}
    for key in group.account_ids:
        valuation = effective[key]
        if valuation.amount is None:
            unknown.append(key)
            continue
        known.append(valuation.amount)
        if key in hypothetical_valuations:
            hypothetical.append(key)
        account = allocations.get(key)
        if account is None:
            by_exposure[None].append(valuation.amount)
            continue
        if account.opening != valuation:
            raise ValueError("resolved sleeve totals must use the snapshot opening valuation")
        if account.mode is InvestmentMode.AGGREGATE:
            by_exposure[None].append(valuation.amount)
            continue
        by_exposure[None].append(account.unclassified_opening)
        for sleeve in account.sleeves:
            if sleeve.basis is OpeningBasis.HYPOTHETICAL and key not in hypothetical:
                hypothetical.append(key)
            if sleeve.basis is OpeningBasis.UNCLASSIFIED:
                by_exposure[None].append(sleeve.amount)
                continue
            weights = models[sleeve.sleeve.investment_id].exposure_weights()
            for exposure_id, amount in apportion(sleeve.amount, weights).items():
                by_exposure.setdefault(exposure_id, []).append(amount)
    total = decimal_sum(known)
    exposures = tuple(ExposureValue(key, decimal_sum(values))
                      for key, values in sorted((key, values) for key, values in by_exposure.items()
                                                if key is not None))
    unclassified = decimal_sum(by_exposure[None])
    if decimal_sum([unclassified, *(item.amount for item in exposures)]) != total:
        raise ArithmeticError("group exposures do not reconcile to the known account values")
    return PortfolioSummary(group, profile.currency, None if unknown else total, total, exposures,
                            unclassified, tuple(unknown), tuple(hypothetical))
