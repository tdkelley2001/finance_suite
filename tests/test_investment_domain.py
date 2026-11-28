"""Independent opening allocation, return, policy, and provenance examples."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import subprocess
import sys
import unittest

from moneylab.configuration.models import AnalysisOverrides, PositionValuationOverride, Scenario
from moneylab.domain.profile import AssetClass, Holding, Owner, Ownership
from moneylab.domain.values import Revision, SourceKind, Valuation
from moneylab.economics import EconomicSeries, SeriesKind
from moneylab.investment.allocation import Allocation, SleeveWeight
from moneylab.investment.exposures import CostKind, ReturnConvention, ReturnTreatment, SeriesExposure, realized_return
from moneylab.investment.inputs import InvestmentReadinessError, OpeningBasis, ResolvedInvestmentInputs
from moneylab.investment.models import (
    AccountInvestmentOverride, AccountInvestmentPlan, Investment, InvestmentMode, InvestmentOverrides,
    InvestmentPlan, InvestmentReturnPreset, InvestmentScenario, ReturnOverride, ReturnTarget,
    SecurityIdentity, Sleeve,
)
from moneylab.investment.policy import (
    ContributionKind, ContributionPolicy, DriftBasis, DriftThreshold, InvestmentPolicy, RebalanceKind,
    RebalancePolicy, WithdrawalKind, WithdrawalPolicy, ZeroTargetRule,
)
from moneylab.investment.portfolio import PortfolioGroup, summarize_portfolio
from moneylab.investment.resolve import resolve_investments, validate_investment_sources
from moneylab.investment.taxonomy import (
    DEFAULT_TAXONOMY, ExposureCategory, ExposureDefinition, ResearchPriority,
)

from test_economic_paths import MARKET, PRICES, explicit_path, static
from test_monthly_projection import ALEX, FEB, JAN, account, profile, snapshot, usd, value


USD = ReturnConvention("USD")
BONDS = EconomicSeries("rates-bonds", SeriesKind.INVESTMENT_RETURN)
EQUITY_ID = "us-equity-broad"
BOND_ID = "us-bond-aggregate"


def constant(rate=0, exposure=None, convention=USD):
    return ReturnTreatment(convention, annual_effective_rate=D(rate), constant_exposure_id=exposure)


def direct(exposure=EQUITY_ID, series=MARKET.id, convention=USD):
    return ReturnTreatment(convention, [SeriesExposure(exposure, series)])


def weights(**fractions):
    return Allocation([SleeveWeight(key, D(weight)) for key, weight in fractions.items()])


def holdings(first, second, *, by_weight=False):
    def holding(key, asset_class, amount):
        data = {"weight": D(amount)} if by_weight else {"value": usd(amount)}
        return Holding(key, asset_class, **data)
    return [holding("stock-holding", AssetClass.EQUITY, first),
            holding("bond-holding", AssetClass.FIXED_INCOME, second)]


def modeled_account(key="brokerage", *, has_reported=True, residual=False, policy=None, fee=None):
    sleeves = [
        Sleeve("equity", "stocks", "stock-holding" if has_reported else None),
        Sleeve("bond", "bonds", "bond-holding" if has_reported else None),
    ]
    if residual:
        sleeves.append(Sleeve("remainder", "custom"))
    return AccountInvestmentPlan(key, InvestmentMode.DETAILED, sleeves,
                                 residual_sleeve_id="remainder" if residual else None,
                                 policy=policy, annual_advisory_fee=fee)


def plan_for(*accounts, investments=None):
    if investments is None:
        investments = [
            Investment("stocks", "Stocks", SecurityIdentity("example-exchange", "EQ"),
                       constant("0", EQUITY_ID)),
            Investment("bonds", "Bonds", treatment=constant("0", BOND_ID)),
            Investment("custom", "Unclassified treatment", treatment=constant()),
        ]
    return InvestmentPlan(Revision("investment-plan", "1"), "profile", accounts, investments)


def financial(*accounts, **kwargs):
    return snapshot(profile(*accounts), rates={}, **kwargs)


def sleeve_values(resolved):
    return {item.id: item.amount for item in resolved.accounts[0].sleeves}


class OpeningInvestmentTests(unittest.TestCase):
    def test_value_and_weight_based_sleeves_reconcile_to_authoritative_account(self):
        plan = plan_for(modeled_account())
        for entries in (holdings(60000, 40000), holdings(".6", ".4", by_weight=True)):
            source = replace(account("brokerage", 100000), holdings=entries)
            snap = financial(source)
            output = resolve_investments(snap, plan)
            self.assertEqual(sleeve_values(output), {"equity": 60000, "bond": 40000})
            self.assertEqual(output.accounts[0].opening.amount, D(100000))
            self.assertEqual(len(snap.profile.accounts), 1)
            self.assertEqual(snap.profile.accounts[0].valuation.amount, D(100000))
            self.assertEqual(output.accounts[0].unclassified_opening, 0)
            output.require_ready()

    def test_opening_rounding_is_exact_order_independent_and_keeps_residual_visible(self):
        source = replace(account("brokerage", ".00000003"), holdings=holdings(".5", ".5", by_weight=True))
        plan = plan_for(modeled_account())
        with localcontext(prec=3):
            result = resolve_investments(financial(source), plan)
        self.assertEqual(sleeve_values(result), {"bond": D(".00000002"), "equity": D(".00000001")})
        self.assertEqual(result.accounts[0].unclassified_opening, 0)
        later = replace(source, holdings=list(reversed(source.holdings)))
        self.assertEqual(resolve_investments(financial(later), plan).content_id, result.content_id)

    def test_incomplete_reported_holdings_keep_twenty_thousand_unclassified(self):
        for entries in (holdings(50000, 30000), holdings(".5", ".3", by_weight=True)):
            source = replace(account("brokerage", 100000), holdings=entries)
            snap = financial(source)
            partial = resolve_investments(snap, plan_for(modeled_account()))
            self.assertEqual(sleeve_values(partial), {"bond": 30000, "equity": 50000})
            self.assertEqual(partial.accounts[0].unclassified_opening, 20000)
            with self.assertRaisesRegex(InvestmentReadinessError, "unclassified_opening_value"):
                partial.require_ready()
            treated = resolve_investments(snap, plan_for(modeled_account(residual=True)))
            self.assertEqual(sleeve_values(treated)["remainder"], 20000)
            residual = next(item for item in treated.accounts[0].sleeves if item.id == "remainder")
            self.assertEqual(residual.basis, OpeningBasis.UNCLASSIFIED)
            treated.require_ready()
            summary = summarize_portfolio(PortfolioGroup(Revision("group", "1"), "Group", ["brokerage"]),
                                          snap, investments=treated)
            self.assertEqual(summary.unclassified_value, 20000)

    def test_hypothetical_valuation_changes_weights_and_retains_reported_dollars(self):
        override = PositionValuationOverride("brokerage", value(150000))
        for entries, expected, remainder in (
            (holdings(60000, 40000), {"equity": 60000, "bond": 40000}, 50000),
            (holdings(".6", ".4", by_weight=True), {"equity": 90000, "bond": 60000}, 0),
        ):
            source = replace(account("brokerage", 100000), holdings=entries)
            snap = financial(source, valuations=[override])
            output = resolve_investments(snap, plan_for(modeled_account()))
            self.assertEqual(sleeve_values(output), expected)
            self.assertEqual(output.accounts[0].unclassified_opening, remainder)
            self.assertEqual(output.accounts[0].valuation_source.kind, SourceKind.LOCAL_OVERRIDE)
            self.assertEqual(output.accounts[0].allocation_source.kind, SourceKind.USER_FACT)
            self.assertEqual(snap.profile.accounts[0], source)

    def test_hypothetical_allocation_replaces_opening_composition_only(self):
        source = replace(account("brokerage", 100000), holdings=holdings(60000, 40000))
        edit = InvestmentOverrides([AccountInvestmentOverride("brokerage", weights(equity=".25", bond=".75"))])
        plan = plan_for(modeled_account(has_reported=False))
        snap = financial(source)
        with self.assertRaisesRegex(ValueError, "must each link"):
            resolve_investments(snap, plan)
        resolved = resolve_investments(snap, plan, local=edit)
        self.assertEqual(sleeve_values(resolved), {"bond": 75000, "equity": 25000})
        self.assertEqual(resolved.accounts[0].allocation_source.kind, SourceKind.LOCAL_OVERRIDE)
        self.assertTrue(all(sleeve.basis is OpeningBasis.HYPOTHETICAL for sleeve in resolved.accounts[0].sleeves))
        self.assertEqual(snap.profile.accounts[0].holdings, source.holdings)
        self.assertEqual(summarize_portfolio(PortfolioGroup(Revision("group", "1"), "Group", ["brokerage"]),
                                             snap, investments=resolved).hypothetical_accounts, ("brokerage",))

    def test_aggregate_and_detailed_inputs_never_combine_the_same_account_return(self):
        source = account("brokerage", 100000)
        snap = financial(source)
        aggregate = AccountInvestmentPlan("brokerage", InvestmentMode.AGGREGATE, aggregate_return=constant(".1"))
        result = resolve_investments(snap, plan_for(aggregate))
        self.assertEqual(result.accounts[0].opening.amount, 100000)
        self.assertEqual(result.accounts[0].unclassified_opening, 100000)
        self.assertFalse(result.accounts[0].sleeves)
        result.require_ready()
        prior_growth = snapshot(profile(source))
        with self.assertRaisesRegex(ValueError, "conflicts with financial snapshot growth"):
            resolve_investments(prior_growth, plan_for(aggregate))
        with self.assertRaisesRegex(ValueError, "detailed sleeves conflict"):
            resolve_investments(prior_growth, plan_for(modeled_account(has_reported=False)))
        with self.assertRaisesRegex(ValueError, "cannot include sleeves"):
            replace(aggregate, sleeves=[Sleeve("equity", "stocks")])


class ReturnResolutionTests(unittest.TestCase):
    def test_core_extended_catalog_and_overlapping_direct_allocations(self):
        self.assertEqual(sum(item.priority is ResearchPriority.CORE for item in DEFAULT_TAXONOMY.definitions), 8)
        self.assertEqual(sum(item.priority is ResearchPriority.EXTENDED for item in DEFAULT_TAXONOMY.definitions), 11)
        broad = DEFAULT_TAXONOMY.require(EQUITY_ID)
        large = DEFAULT_TAXONOMY.require("us-equity-large-cap")
        self.assertEqual(broad.category, large.category)
        self.assertNotEqual(broad.id, large.id)
        self.assertEqual(DEFAULT_TAXONOMY.revision.version, "1.0.0")

    def test_fixed_composite_return_is_four_percent_without_updating_balances(self):
        path = explicit_path((MARKET, [".10"]), (BONDS, ["-.05"]), (PRICES, [".01"]))
        treatment = ReturnTreatment(USD, [
            SeriesExposure(EQUITY_ID, MARKET.id, D(".6")), SeriesExposure(BOND_ID, BONDS.id, D(".4")),
        ], mapping_revision=Revision("fund-mix", "1"))
        self.assertEqual(realized_return(treatment, currency="USD", path=path, month_on=JAN), D(".04"))
        with self.assertRaisesRegex(ValueError, "weights must sum to one"):
            replace(treatment, series=treatment.series[:1])
        with self.assertRaisesRegex(ValueError, "covered first-of-month"):
            realized_return(treatment, currency="USD", path=path, month_on=FEB)
        with self.assertRaisesRegex(ValueError, "investment return series"):
            realized_return(direct(series=PRICES.id), currency="USD", path=path, month_on=JAN)
        with self.assertRaisesRegex(ValueError, "investment return series"):
            realized_return(direct(series="missing"), currency="USD", path=path, month_on=JAN)
        with self.assertRaisesRegex(ValueError, "projection currency"):
            realized_return(direct(convention=ReturnConvention("EUR")), currency="USD", path=path, month_on=JAN)

    def test_custom_direct_annual_and_static_treatments_are_explicit(self):
        custom = ExposureDefinition("custom.strategy", "Strategy", ExposureCategory.OTHER, ResearchPriority.CUSTOM)
        taxonomy = replace(DEFAULT_TAXONOMY, revision=Revision(DEFAULT_TAXONOMY.revision.id, "custom-1"),
                           definitions=[*DEFAULT_TAXONOMY.definitions, custom])
        path = explicit_path((MARKET, ["-.25"]))
        return_input = direct(custom.id)
        self.assertEqual(realized_return(return_input, currency="USD", taxonomy=taxonomy,
                                         path=path, month_on=JAN), D("-.25"))
        with self.assertRaisesRegex(ValueError, "unknown economic exposure"):
            realized_return(return_input, currency="USD", path=path, month_on=JAN)
        monthly = realized_return(constant(".12", custom.id), currency="USD", taxonomy=taxonomy)
        self.assertAlmostEqual((1 + monthly) ** 12, D("1.12"), delta=D("1e-25"))
        self.assertEqual(realized_return(constant(), currency="USD"), 0)
        for bad in (
            lambda: ReturnTreatment(USD), lambda: replace(return_input, annual_effective_rate=D(0)),
            lambda: constant("NaN"), lambda: constant("-1"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bad()

    def test_distinct_investments_share_one_economic_series_and_holdings_stay_separate(self):
        path = explicit_path((MARKET, [".10"]))
        accounts = [replace(account(key, 100), holdings=[Holding("holding", AssetClass.EQUITY, weight=D(1))])
                    for key in ("one", "two")]
        methods = [
            Investment(key, key, SecurityIdentity("venue", key.upper()), direct())
            for key in ("first", "second")
        ]
        plans = [
            AccountInvestmentPlan(account.id, InvestmentMode.DETAILED, [Sleeve("equity", key, "holding")])
            for account, key in zip(accounts, ("first", "second"))
        ]
        snap = financial(*accounts)
        resolved = resolve_investments(snap, plan_for(*plans, investments=methods), path=path)
        self.assertEqual([item.opening.amount for item in resolved.accounts], [100, 100])
        self.assertEqual([realized_return(item.investment.treatment, currency="USD", path=path, month_on=JAN)
                          for item in resolved.investments], [D(".1"), D(".1")])
        self.assertNotEqual(resolved.investments[0].investment.security, resolved.investments[1].investment.security)
        self.assertEqual(resolved.economic_path_content_id, path.content_id)

    def test_embedded_expenses_and_advisory_fees_are_distinct_and_cannot_repeat(self):
        source = replace(account("brokerage", 100000), holdings=holdings(60000, 40000))
        net_fund = ReturnConvention("USD", [CostKind.FUND_EXPENSE])
        stock = Investment("stocks", "Stocks", treatment=constant(".07", EQUITY_ID, net_fund))
        bonds = Investment("bonds", "Bonds", treatment=constant(".04", BOND_ID),
                           annual_fund_expense=D(".0005"))
        plan = plan_for(modeled_account(fee=D(".005")), investments=[stock, bonds])
        snap = financial(source)
        result = resolve_investments(snap, plan)
        self.assertEqual(result.accounts[0].annual_advisory_fee, D(".005"))
        self.assertEqual(result.investments[0].investment.annual_fund_expense, D(".0005"))
        self.assertEqual(result.investments[1].investment.treatment.convention.embedded_costs, (CostKind.FUND_EXPENSE,))
        self.assertEqual(result.accounts[0].opening.amount, 100000)
        with self.assertRaisesRegex(ValueError, "double count an embedded cost"):
            resolve_investments(snap, replace(plan, investments=[replace(stock, annual_fund_expense=D(".01")), bonds]))
        already_advised = replace(stock, treatment=constant(".07", EQUITY_ID,
                                                           ReturnConvention("USD", [CostKind.ADVISORY_FEE])))
        with self.assertRaisesRegex(ValueError, "separate advisory_fee would double count"):
            resolve_investments(snap, replace(plan, investments=[already_advised, bonds]))
        with self.assertRaisesRegex(ValueError, "conflicting return conventions"):
            resolve_investments(snap, replace(plan, investments=[
                replace(stock, treatment=direct(convention=net_fund)),
                replace(bonds, treatment=direct(BOND_ID)),
            ]), path=explicit_path((MARKET, [".1"])))


class InvestmentPolicyTests(unittest.TestCase):
    def test_current_seventy_thirty_and_target_sixty_forty_remain_separate(self):
        source = replace(account("brokerage", 100000), holdings=holdings(70000, 30000))
        target = weights(equity=".6", bond=".4")
        policy = InvestmentPolicy(
            Revision("policy", "1"), target,
            ContributionPolicy(ContributionKind.REBALANCE_DIRECTED),
            WithdrawalPolicy(WithdrawalKind.REBALANCE_DIRECTED),
            RebalancePolicy(RebalanceKind.CALENDAR, [12]),
        )
        result = resolve_investments(financial(source), plan_for(modeled_account(policy=policy)))
        stored = result.accounts[0]
        self.assertEqual(stored.current_weights(), {"equity": D(".7"), "bond": D(".3")})
        self.assertEqual(stored.policy.target, target)
        self.assertEqual(sleeve_values(result), {"equity": 70000, "bond": 30000})
        result.require_ready()

    def test_zero_portfolio_retains_future_targets_and_requires_explicit_current_fallback(self):
        source = account("brokerage", 0)
        target = weights(equity=".6", bond=".4")
        policy = InvestmentPolicy(Revision("policy", "1"), target, ContributionPolicy(ContributionKind.CURRENT))
        plan = plan_for(modeled_account(has_reported=False, policy=policy))
        resolved = resolve_investments(financial(source), plan)
        self.assertIsNone(resolved.accounts[0].current_weights())
        self.assertEqual(sleeve_values(resolved), {"equity": 0, "bond": 0})
        self.assertTrue(all(item.basis is OpeningBasis.FUTURE_DESTINATION for item in resolved.accounts[0].sleeves))
        with self.assertRaisesRegex(InvestmentReadinessError, "missing_zero_balance_fallback"):
            resolved.require_ready()
        funded = replace(policy, contribution=ContributionPolicy(ContributionKind.CURRENT,
                                                                  zero_balance_fallback=target))
        local = InvestmentOverrides([AccountInvestmentOverride("brokerage", policy=funded)])
        ready = resolve_investments(financial(source), plan, local=local)
        self.assertIsNone(ready.accounts[0].current_weights())
        self.assertEqual(ready.accounts[0].policy.contribution.zero_balance_fallback, target)
        ready.require_ready()

    def test_policy_requirements_and_calendar_drift_validation(self):
        ref = Revision("policy", "1")
        target = weights(equity="1", bond="0")
        absolute = DriftThreshold(DriftBasis.ABSOLUTE, D(".05"))
        relative = DriftThreshold(DriftBasis.RELATIVE, D(".25"))
        for case in (
            lambda: ContributionPolicy(ContributionKind.CUSTOM),
            lambda: ContributionPolicy(ContributionKind.TARGET, zero_balance_fallback=target),
            lambda: InvestmentPolicy(ref, contribution=ContributionPolicy(ContributionKind.TARGET)),
            lambda: WithdrawalPolicy(WithdrawalKind.CUSTOM),
            lambda: WithdrawalPolicy(WithdrawalKind.CASH_FIRST, cash_sleeve_id="cash"),
            lambda: RebalancePolicy(RebalanceKind.NONE, [12]),
            lambda: RebalancePolicy(RebalanceKind.CALENDAR, [13]),
            lambda: RebalancePolicy(RebalanceKind.CALENDAR_OR_THRESHOLD, [12]),
            lambda: RebalancePolicy(RebalanceKind.THRESHOLD, [3], absolute),
            lambda: DriftThreshold(DriftBasis.ABSOLUTE, D("1.01")),
            lambda: InvestmentPolicy(ref, target, rebalance=RebalancePolicy(RebalanceKind.THRESHOLD,
                                                                            threshold=relative)),
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                case()
        explicit = replace(relative, zero_target=ZeroTargetRule.ANY_POSITIVE)
        either = InvestmentPolicy(ref, target, rebalance=RebalancePolicy(
            RebalanceKind.CALENDAR_OR_THRESHOLD, [12, 3, 6, 9], explicit,
        ))
        scheduled_check = replace(either, rebalance=replace(either.rebalance, kind=RebalanceKind.THRESHOLD_ON_SCHEDULE))
        self.assertEqual(either.rebalance.calendar_months, (3, 6, 9, 12))
        self.assertNotEqual(either.rebalance.kind, scheduled_check.rebalance.kind)
        alternate = replace(explicit, zero_target=ZeroTargetRule.ABSOLUTE, zero_target_fraction=D(".02"))
        self.assertEqual(alternate.zero_target_fraction, D(".02"))
        self.assertEqual(either.target.weights[0].weight, D(0))

    def test_cash_first_requires_a_cash_exposure_and_explicit_secondary_policy(self):
        source = replace(account("brokerage", 100), holdings=holdings(".7", ".3", by_weight=True))
        policy = InvestmentPolicy(
            Revision("policy", "1"),
            withdrawal=WithdrawalPolicy(WithdrawalKind.CASH_FIRST, cash_sleeve_id="cash", secondary=WithdrawalPolicy(
                WithdrawalKind.CUSTOM, custom=weights(equity="1", bond="0", cash="0"),
            )),
        )
        detail = modeled_account(policy=policy)
        baseline = plan_for(detail)
        detail = replace(detail, sleeves=[*detail.sleeves, Sleeve("cash", "cash-model")])
        models = (*baseline.investments, Investment("cash-model", "Cash model", treatment=constant(exposure="cash")))
        plan = plan_for(detail, investments=models)
        ready = resolve_investments(financial(source), plan)
        ready.require_ready()
        self.assertEqual(ResolvedInvestmentInputs.from_json(ready.to_json()), ready)
        wrong = (*models[:-1], replace(models[-1], treatment=constant(exposure=EQUITY_ID)))
        with self.assertRaisesRegex(ValueError, "explicitly cash-exposed"):
            resolve_investments(financial(source), replace(plan, investments=wrong))
        missing_destination = replace(policy, contribution=ContributionPolicy(
            ContributionKind.CUSTOM, custom=weights(equity=".6", bond=".4"),
        ))
        with self.assertRaisesRegex(ValueError, "every modeled sleeve"):
            resolve_investments(financial(source), plan_for(replace(detail, policy=missing_destination),
                                                            investments=models))


class InvestmentConfigurationTests(unittest.TestCase):
    def test_saved_and_local_layers_override_fields_without_mutating_baselines(self):
        source = replace(account("brokerage", 100000), holdings=holdings(70000, 30000))
        baseline_policy = InvestmentPolicy(Revision("original-policy", "1"), weights(equity=".6", bond=".4"))
        plan = plan_for(modeled_account(policy=baseline_policy))
        shot = financial(source)
        baseline = resolve_investments(shot, plan)

        scenario = Scenario(Revision("plan-b", "2"), "Plan B", "profile")
        scenario_shot = financial(source, scenario=scenario)
        scenario_policy = InvestmentPolicy(Revision("plan-b-policy", "1"), weights(equity=".3", bond=".7"))
        saved = InvestmentScenario(scenario.revision, plan.revision.id, InvestmentOverrides(
            [AccountInvestmentOverride("brokerage", weights(equity=".4", bond=".6"), scenario_policy)],
            [ReturnOverride(ReturnTarget.INVESTMENT, "stocks", constant(".07", EQUITY_ID))],
        ))
        local = InvestmentOverrides(
            [AccountInvestmentOverride("brokerage", weights(equity=".2", bond=".8"))],
            [ReturnOverride(ReturnTarget.INVESTMENT, "stocks", constant(".08", EQUITY_ID))],
        )
        case = resolve_investments(scenario_shot, plan, scenario=saved)
        comparison = resolve_investments(scenario_shot, plan, scenario=saved, local=local)
        self.assertEqual(sleeve_values(baseline), {"equity": 70000, "bond": 30000})
        self.assertEqual(sleeve_values(case), {"equity": 40000, "bond": 60000})
        self.assertEqual(sleeve_values(comparison), {"equity": 20000, "bond": 80000})
        self.assertEqual(comparison.accounts[0].policy, scenario_policy)
        self.assertEqual(comparison.accounts[0].policy_source.reference, scenario.revision)
        self.assertEqual(comparison.accounts[0].allocation_source.kind, SourceKind.LOCAL_OVERRIDE)
        self.assertEqual(comparison.investments[1].investment.treatment.annual_effective_rate, D(".08"))
        self.assertEqual(comparison.investments[1].return_source.kind, SourceKind.LOCAL_OVERRIDE)
        self.assertEqual(resolve_investments(shot, plan), baseline)
        self.assertEqual(plan.accounts[0].policy, baseline_policy)
        self.assertEqual(scenario_shot.profile.accounts[0].holdings, source.holdings)
        with self.assertRaisesRegex(ValueError, "must match"):
            resolve_investments(shot, plan, scenario=saved)

    def test_return_only_layers_follow_precedence_without_inventing_holdings(self):
        account_request = AccountInvestmentPlan("brokerage", InvestmentMode.AGGREGATE)
        source = financial(account("brokerage", 1000))
        ref = plan_for(account_request)
        preset = InvestmentReturnPreset(Revision("method-preset", "1"), [
            ReturnOverride(ReturnTarget.ACCOUNT, "brokerage", constant(".03")),
        ])
        defaults = InvestmentReturnPreset(Revision("research", "1"), [
            ReturnOverride(ReturnTarget.ACCOUNT, "brokerage", constant(".01")),
        ])
        with self.assertRaisesRegex(ValueError, "explicit return treatment"):
            resolve_investments(source, ref)
        prescribed = resolve_investments(source, ref, preset=preset, research_defaults=defaults)
        self.assertEqual(prescribed.accounts[0].aggregate_return_source.kind, SourceKind.PRESET)
        self.assertEqual(prescribed.accounts[0].aggregate_return.annual_effective_rate, D(".03"))
        fallback = resolve_investments(source, ref, research_defaults=defaults)
        self.assertEqual(fallback.accounts[0].aggregate_return_source.kind, SourceKind.RESEARCH_DEFAULT)
        personal = resolve_investments(source, plan_for(replace(account_request, aggregate_return=constant(0))),
                                       preset=preset)
        self.assertEqual(personal.accounts[0].aggregate_return.annual_effective_rate, 0)
        self.assertEqual(personal.accounts[0].unclassified_opening, 1000)
        with self.assertRaisesRegex(ValueError, "only typed return"):
            resolve_investments(source, ref, preset=InvestmentOverrides())
        with self.assertRaisesRegex(ValueError, "ineligible"):
            resolve_investments(source, ref, local=InvestmentOverrides(returns=[
                ReturnOverride(ReturnTarget.INVESTMENT, "stocks", constant(0)),
            ]))

    def test_rejects_missing_out_of_scope_and_partially_owned_accounts(self):
        plan = plan_for(modeled_account(has_reported=False))
        for source in (
            financial(account("not-brokerage", 0)),
            financial(account("brokerage", 100, ownership=Ownership([Owner("blair")]))),
            financial(account("brokerage", 100, ownership=Ownership([Owner("alex"), Owner("blair")]))),
        ):
            with self.assertRaisesRegex(ValueError, "existing in-scope, fully covered"):
                resolve_investments(source, plan)
        with self.assertRaisesRegex(ValueError, "known investments"):
            plan_for(modeled_account(), investments=[Investment("stocks", "Stocks", treatment=constant(0))])
        with self.assertRaisesRegex(ValueError, "calendar horizon"):
            resolve_investments(financial(account("brokerage", 100)), plan,
                                path=explicit_path((MARKET, [".1", ".1"])))

    def test_resolved_inputs_round_trip_are_immutable_and_sensitive_to_effective_inputs(self):
        levels = [SleeveWeight("equity", D(".5")), SleeveWeight("bond", D(".5"))]
        allocation = Allocation(levels)
        registered = [Investment("stocks", "Stocks", treatment=direct()),
                      Investment("bonds", "Bonds", treatment=constant(exposure=BOND_ID))]
        plan = plan_for(modeled_account(has_reported=False), investments=registered)
        registered.clear()
        source = financial(account("brokerage", 10))
        path = explicit_path((MARKET, [".1"]))
        overrides = [AccountInvestmentOverride("brokerage", allocation)]
        local = InvestmentOverrides(overrides)
        resolved = resolve_investments(source, plan, path=path, local=local)
        before = resolved.to_json()
        levels.clear()
        overrides.clear()
        with self.assertRaises(FrozenInstanceError):
            resolved.accounts[0].sleeves[0].amount = D(123)
        self.assertEqual(resolved.to_json(), before)
        loaded = ResolvedInvestmentInputs.from_json(before)
        self.assertEqual(loaded, resolved)
        self.assertEqual(loaded.content_id, resolved.content_id)
        self.assertEqual(loaded.snapshot_content_id, source.content_id)
        self.assertEqual(json.loads(before)["taxonomy"]["revision"]["version"], "1.0.0")
        validate_investment_sources(loaded, source, path=path)
        with self.assertRaisesRegex(ValueError, "recorded economic path"):
            validate_investment_sources(loaded, source, path=explicit_path((MARKET, [".2"])))
        with self.assertRaisesRegex(ValueError, "recorded financial snapshot"):
            validate_investment_sources(loaded, financial(account("brokerage", 11)), path=path)
        allocations = InvestmentOverrides([AccountInvestmentOverride("brokerage", weights(equity="1", bond="0"))])
        cases = [
            resolve_investments(source, plan, path=path, local=allocations),
            resolve_investments(source, plan, path=explicit_path((MARKET, [".2"])), local=local),
            resolve_investments(source, plan, path=path, local=replace(local, returns=[
                ReturnOverride(ReturnTarget.INVESTMENT, "stocks", direct("us-equity-large-cap")),
            ])),
            resolve_investments(source, plan, path=path, local=InvestmentOverrides([
                AccountInvestmentOverride("brokerage", allocation,
                                          InvestmentPolicy(Revision("policy", "1"), weights(equity="1", bond="0"))),
            ])),
        ]
        self.assertTrue(all(item.content_id != resolved.content_id for item in cases))
        reopened = json.loads(before)
        reopened["accounts"][0]["sleeves"][0]["amount"] = "99"
        with self.assertRaisesRegex(ValueError, "do not reconcile"):
            ResolvedInvestmentInputs.from_json(json.dumps(reopened))


class PortfolioGroupingTests(unittest.TestCase):
    def test_overlapping_groups_count_each_existing_account_once(self):
        brokerage = replace(account("brokerage", 100000), holdings=holdings(50000, 30000))
        snap = financial(brokerage, account("cash-account", 5000))
        plan = plan_for(modeled_account())
        allocations = resolve_investments(snap, plan)
        total = PortfolioGroup(Revision("total", "1"), "Total", ["brokerage", "cash-account"])
        invest = PortfolioGroup(Revision("invest", "1"), "Investments", ["brokerage"])
        result = summarize_portfolio(total, snap, investments=allocations)
        self.assertEqual(result.total, 105000)
        self.assertEqual(result.known_total, 105000)
        self.assertEqual(result.unclassified_value, 25000)
        self.assertEqual({item.exposure_id: item.amount for item in result.exposures},
                         {EQUITY_ID: 50000, BOND_ID: 30000})
        self.assertEqual(summarize_portfolio(invest, snap, investments=allocations).total, 100000)
        self.assertEqual(len(snap.profile.accounts), 2)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            replace(total, account_ids=["brokerage", "brokerage"])
        with self.assertRaisesRegex(ValueError, "fully covered"):
            summarize_portfolio(replace(total, account_ids=["unknown"]), snap)
        different = financial(replace(brokerage, name="Renamed"), account("cash-account", 5000))
        with self.assertRaisesRegex(ValueError, "match the financial snapshot"):
            summarize_portfolio(total, different, investments=allocations)

    def test_unavailable_account_values_differ_from_known_zero(self):
        records = profile(account("empty", 0), account("valued", 100),
                          replace(account("unknown", 0), valuation=Valuation("USD")))
        group = PortfolioGroup(Revision("investment-group", "1"), "Investment group", ["empty", "unknown"])
        summary = summarize_portfolio(group, records, subject=ALEX)
        self.assertIsNone(summary.total)
        self.assertEqual(summary.known_total, 0)
        self.assertEqual(summary.unknown_value_accounts, ("unknown",))
        known = summarize_portfolio(replace(group, account_ids=["empty"]), records, subject=ALEX)
        self.assertEqual(known.total, 0)
        self.assertEqual(known.unknown_value_accounts, ())
        self.assertIsNone(known.exposure_weights())
        incomplete = summarize_portfolio(replace(group, account_ids=["valued", "unknown"]), records, subject=ALEX)
        self.assertEqual(incomplete.known_total, 100)
        self.assertIsNone(incomplete.exposure_weights())

    def test_stdlib_boundary_and_existing_execution_interfaces(self):
        from moneylab.projection import project_economic_path, project_monthly

        records = profile(account("brokerage", 100))
        legacy = snapshot(records, rates={"brokerage": "0"})
        detail = AccountInvestmentPlan("brokerage", InvestmentMode.AGGREGATE, aggregate_return=constant())
        resolve_investments(legacy, plan_for(detail)).require_ready()
        self.assertEqual(project_monthly(legacy).months[0].closing.net_worth, 100)
        path = explicit_path((MARKET, [".2"]))
        self.assertEqual(project_economic_path(legacy, path, [static("brokerage")]).projection.months[0].closing.net_worth, 100)

        root = Path(__file__).resolve().parents[1]
        command = (
            'import sys; sys.path[:0] = sys.argv[1:]; '
            'from test_investment_domain import *; '
            'result = resolve_investments(financial(account("brokerage", 0)), '
            'plan_for(modeled_account(has_reported=False))); '
            'assert result.accounts[0].opening.amount == 0'
        )
        run = subprocess.run([sys.executable, "-I", "-S", "-c", command, str(root), str(root / "tests")],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
