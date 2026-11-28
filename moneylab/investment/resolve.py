"""Resolve investment configuration against effective financial opening values."""

from dataclasses import replace
from decimal import localcontext

from moneylab.configuration.models import AnalysisType
from moneylab.configuration.snapshot import ResolvedAnalysis, position_valuation_field
from moneylab.domain.profile import Account, FinancialProfile, Subject
from moneylab.domain.values import Source, SourceKind, decimal_sum
from moneylab.economics import EconomicPath
from moneylab.economics.rates import CALCULATION_CONTEXT

from .allocation import ONE, ZERO, apportion
from .inputs import OpeningBasis, ResolvedAccount, ResolvedInvestment, ResolvedInvestmentInputs, ResolvedSleeve
from .models import (
    InvestmentMode, InvestmentOverrides, InvestmentPlan, InvestmentReturnPreset, InvestmentScenario,
    ReturnTarget,
)
from .taxonomy import DEFAULT_TAXONOMY, ExposureTaxonomy


def scoped_accounts(profile: FinancialProfile, subject: Subject) -> dict[str, Account]:
    """Select only whole accounts under the financially supported ownership scope."""
    members = profile.people_in(subject)
    return {item.id: item for item in profile.positions_for(subject)
            if isinstance(item, Account) and item.ownership.person_ids() <= members}


def _reported_sleeves(plan, holdings, total):
    links = {sleeve.holding_id for sleeve in plan.sleeves if sleeve.holding_id is not None}
    if links != holdings.keys():
        raise ValueError(f"{plan.account_id}: detailed reported holdings must each link to a sleeve")

    if any(holding.weight is not None for holding in holdings.values()):
        weights = {item.id: holdings[item.holding_id].weight for item in plan.sleeves
                   if item.holding_id is not None}
        weights[None] = ONE - decimal_sum(weights.values())
        allocated = apportion(total, weights)
        amounts = {key: amount for key, amount in allocated.items() if key is not None}
        remainder = allocated[None]
    else:
        amounts = {item.id: holdings[item.holding_id].value.amount for item in plan.sleeves
                   if item.holding_id is not None}
        remainder = total - decimal_sum(amounts.values())
    if remainder < ZERO:
        raise ValueError(f"{plan.account_id}: reported sleeve values exceed the effective opening value")

    sleeves = []
    for model in plan.sleeves:
        if model.holding_id is not None:
            sleeves.append(ResolvedSleeve(model, amounts[model.id], OpeningBasis.REPORTED,
                                          holdings[model.holding_id].weight))
        elif model.id == plan.residual_sleeve_id:
            sleeves.append(ResolvedSleeve(model, remainder, OpeningBasis.UNCLASSIFIED))
        else:
            sleeves.append(ResolvedSleeve(model, ZERO, OpeningBasis.FUTURE_DESTINATION))
    return tuple(sleeves), remainder if plan.residual_sleeve_id is None else ZERO


def _opening_sleeves(plan, account, total, allocation):
    holdings = {item.id: item for item in account.holdings}
    if any(item.holding_id is not None and item.holding_id not in holdings for item in plan.sleeves):
        raise ValueError(f"{account.id}: sleeve references an unknown holding")
    with localcontext(CALCULATION_CONTEXT):
        if allocation is None:
            return _reported_sleeves(plan, holdings, total)
        weights = {item.sleeve_id: item.weight for item in allocation.weights}
        amounts = apportion(total, weights)
        return tuple(ResolvedSleeve(item, amounts[item.id], OpeningBasis.HYPOTHETICAL, weights[item.id])
                     for item in plan.sleeves), ZERO


def _apply_account_overrides(plan_accounts, layers):
    allocations, policies = {}, {}
    for overrides, source in layers:
        for override in overrides.accounts:
            account = plan_accounts.get(override.account_id)
            if account is None or account.mode is not InvestmentMode.DETAILED:
                raise ValueError(f"{override.account_id}: allocation and policy overrides require a detailed plan")
            if override.allocation is not None:
                override.allocation.require_destinations({item.id for item in account.sleeves})
                allocations.setdefault(account.account_id, (override.allocation, source))
            if override.policy is not None:
                policies.setdefault(account.account_id, (override.policy, source))
    return allocations, policies


def _effective_returns(plan, models, layers, presets, currency, taxonomy, path, baseline_source):
    base = {}
    for account in plan.accounts:
        if account.mode is InvestmentMode.AGGREGATE:
            base[(ReturnTarget.ACCOUNT, account.account_id)] = (
                account.aggregate_return, account.source or baseline_source,
            )
    for model in models.values():
        base[(ReturnTarget.INVESTMENT, model.id)] = model.treatment, model.source or baseline_source

    selected = {}

    def select(records, source):
        for entry in records:
            key = (entry.target, entry.id)
            if key not in base:
                raise ValueError(f"{entry.id}: return override references an ineligible {entry.target.value}")
            selected.setdefault(key, (entry.treatment, source))

    for overrides, source in layers:
        select(overrides.returns, source)
    for key, (treatment, source) in base.items():
        if treatment is not None:
            selected.setdefault(key, (treatment, source))
    for records, source in presets:
        select(records, source)
    for key in base:
        if key not in selected:
            raise ValueError(f"{key[1]} requires an explicit return treatment")
        selected[key][0].validate(currency, taxonomy, path)
    return selected


def resolve_investments(
    snapshot: ResolvedAnalysis, plan: InvestmentPlan, *,
    path: EconomicPath | None = None, taxonomy: ExposureTaxonomy = DEFAULT_TAXONOMY,
    scenario: InvestmentScenario | None = None, local: InvestmentOverrides | None = None,
    preset: InvestmentReturnPreset | None = None, research_defaults: InvestmentReturnPreset | None = None,
) -> ResolvedInvestmentInputs:
    """Capture return treatments and opening allocations without modifying the snapshot."""
    if (not isinstance(snapshot, ResolvedAnalysis)
            or snapshot.request.analysis_type is not AnalysisType.MONTHLY_PROJECTION):
        raise ValueError("investment inputs require a monthly financial snapshot")
    if not isinstance(plan, InvestmentPlan) or plan.profile_id != snapshot.profile.revision.id:
        raise ValueError("investment plan must reference the snapshot's financial profile")
    if not isinstance(taxonomy, ExposureTaxonomy):
        raise ValueError("expected a versioned investment taxonomy")
    request = snapshot.request.inputs
    if path is not None and (
        not isinstance(path, EconomicPath) or path.start_on != request.start_on
        or path.horizon_months != snapshot.preferences.horizon_months
    ):
        raise ValueError("economic path must match the financial snapshot's calendar horizon")
    if scenario is not None and (
        not isinstance(scenario, InvestmentScenario) or scenario.plan_id != plan.revision.id
        or scenario.scenario_revision != snapshot.scenario_revision
    ):
        raise ValueError("investment scenario must match the resolved financial scenario and investment plan")
    if local is not None and not isinstance(local, InvestmentOverrides):
        raise ValueError("expected typed local investment overrides")

    profile = snapshot.profile
    accounts = scoped_accounts(profile, request.subject)
    plan_accounts = {item.account_id: item for item in plan.accounts}
    if not plan_accounts.keys() <= accounts.keys():
        raise ValueError("investment plans require existing in-scope, fully covered accounts")
    used = {sleeve.investment_id for account in plan.accounts for sleeve in account.sleeves}
    models = {item.id: item for item in plan.investments if item.id in used}
    baseline_source = Source(SourceKind.USER_PLAN, plan.revision)
    layers = []
    if local is not None:
        layers.append((local, Source(SourceKind.LOCAL_OVERRIDE)))
    if scenario is not None:
        layers.append((scenario.overrides, Source(SourceKind.SCENARIO_OVERRIDE, scenario.scenario_revision)))
    presets = []
    for config, kind in ((preset, SourceKind.PRESET), (research_defaults, SourceKind.RESEARCH_DEFAULT)):
        if config is not None:
            if not isinstance(config, InvestmentReturnPreset):
                raise ValueError("investment presets and defaults accept only typed return assumptions")
            presets.append((config.returns, Source(kind, config.revision)))
    allocations, policies = _apply_account_overrides(plan_accounts, layers)
    returns = _effective_returns(plan, models, layers, presets, profile.currency, taxonomy, path, baseline_source)
    investments = []
    for key, model in models.items():
        treatment, source = returns[(ReturnTarget.INVESTMENT, key)]
        investments.append(ResolvedInvestment(replace(model, treatment=treatment), source))

    opening = snapshot.opening_valuations()
    financial_origins = {item.field: item.source for item in snapshot.origins}
    deterministic = {item.position_id: item.annual_effective_rate for item in snapshot.position_growth}
    resolved = []
    for item in plan.accounts:
        key = item.account_id
        account = accounts[key]
        valuation = opening[key]
        factual_source = account.source or Source(SourceKind.USER_FACT, profile.revision)
        valuation_source = financial_origins.get(position_valuation_field(key), factual_source)
        if item.mode is InvestmentMode.AGGREGATE:
            treatment, source = returns[(ReturnTarget.ACCOUNT, key)]
            if key in deterministic and treatment.annual_effective_rate != deterministic[key]:
                raise ValueError(f"{key}: aggregate return conflicts with financial snapshot growth")
            resolved.append(ResolvedAccount(
                key, valuation, valuation_source, item.mode, unclassified_opening=valuation.amount,
                aggregate_return=treatment, aggregate_return_source=source,
                annual_advisory_fee=item.annual_advisory_fee,
            ))
        else:
            if key in deterministic:
                raise ValueError(f"{key}: detailed sleeves conflict with aggregate financial snapshot growth")
            allocation, allocation_source = allocations.get(key, (None, factual_source))
            policy = item.policy
            policy, policy_source = policies.get(
                key, (policy, (policy.source or item.source or baseline_source) if policy is not None else None),
            )
            sleeves, residual = _opening_sleeves(item, account, valuation.amount, allocation)
            resolved.append(ResolvedAccount(
                key, valuation, valuation_source, item.mode, sleeves, residual, allocation_source,
                annual_advisory_fee=item.annual_advisory_fee, policy=policy, policy_source=policy_source,
            ))
    return ResolvedInvestmentInputs(
        snapshot_content_id=snapshot.content_id, snapshot_schema_version=snapshot.schema_version,
        plan_revision=plan.revision, taxonomy=taxonomy, currency=profile.currency, start_on=request.start_on,
        accounts=resolved, investments=investments,
        economic_path_content_id=None if path is None else path.content_id,
        economic_path_schema_version=None if path is None else path.schema_version,
        scenario_revision=None if scenario is None else scenario.scenario_revision,
        preset_revision=None if preset is None else preset.revision,
        defaults_revision=None if research_defaults is None else research_defaults.revision,
    )


def validate_investment_sources(
    inputs: ResolvedInvestmentInputs, snapshot: ResolvedAnalysis, *, path: EconomicPath | None = None,
) -> None:
    """Verify reloaded records against the exact financial and economic inputs."""
    if (not isinstance(inputs, ResolvedInvestmentInputs) or not isinstance(snapshot, ResolvedAnalysis)
            or snapshot.request.analysis_type is not AnalysisType.MONTHLY_PROJECTION
            or (inputs.snapshot_content_id, inputs.snapshot_schema_version)
            != (snapshot.content_id, snapshot.schema_version)):
        raise ValueError("investment inputs must use the recorded financial snapshot")
    if path is not None and not isinstance(path, EconomicPath):
        raise ValueError("expected the recorded economic path")
    path_reference = (None, None) if path is None else (path.content_id, path.schema_version)
    if (inputs.economic_path_content_id, inputs.economic_path_schema_version) != path_reference:
        raise ValueError("investment inputs must use the recorded economic path")
    request = snapshot.request.inputs
    if inputs.start_on != request.start_on or inputs.currency != snapshot.profile.currency:
        raise ValueError("investment inputs must use the snapshot opening date and currency")
    if path is not None and (
        path.start_on != request.start_on or path.horizon_months != snapshot.preferences.horizon_months
    ):
        raise ValueError("recorded path must cover the snapshot's calendar horizon")
    accounts = scoped_accounts(snapshot.profile, request.subject)
    opening = snapshot.opening_valuations()
    for account in inputs.accounts:
        if account.account_id not in accounts or account.opening != opening[account.account_id]:
            raise ValueError("investment opening values must match in-scope snapshot accounts")
        if account.aggregate_return is not None:
            account.aggregate_return.validate(inputs.currency, inputs.taxonomy, path)
    for model in inputs.investments:
        model.investment.treatment.validate(inputs.currency, inputs.taxonomy, path)
