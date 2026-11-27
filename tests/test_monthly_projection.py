"""Independent financial reference cases and projection boundary checks."""

from dataclasses import replace
from datetime import date
from decimal import Decimal as D, localcontext
import json
import math
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

from moneylab.configuration.models import (
    ActivityAmountOverride, AnalysisOverrides, AnalysisRequest, AnalysisType, EconomicAssumptions,
    LoanPaymentInputs, ModelPreferences, MonthlyProjectionInputs, PositionGrowth,
    PositionValuationOverride, Scenario, StochasticExecution,
)
from moneylab.configuration.resolve import resolve_analysis
from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.planning import (
    ActivityKind, DebtPaymentSplit, FinancialPlan, Frequency, RecurringActivity, ScheduledAmountChange,
)
from moneylab.domain.profile import (
    Access, Account, AccountKind, Asset, AssetClass, AssetKind, DebtTerms, FinancialProfile, Holding, Household,
    Liability, LiabilityKind, Owner, Ownership, Person, RateKind, Subject, SubjectKind,
)
from moneylab.domain.values import Money, Revision, SourceKind, Valuation
from moneylab.projection import METHODOLOGY, ProjectionReadinessError, project_monthly
from moneylab.projection.accounting import ReconciliationError, reconcile
from moneylab.projection.results import EffectKind, FinancialEffect, PositionKind, Posting, ProjectionStatus


JAN = date(2030, 1, 1)
FEB = date(2030, 2, 1)
MAR = date(2030, 3, 1)
APR = date(2030, 4, 1)
ALEX = Subject(SubjectKind.PERSON, "alex")
HOUSE = Subject(SubjectKind.HOUSEHOLD, "house")
SOLE = Ownership([Owner("alex")])


def usd(amount):
    return Money(D(amount), "USD")


def value(amount, as_of=JAN):
    return Valuation("USD", D(amount), as_of)


def account(key, amount, *, access=Access.UNRESTRICTED, ownership=SOLE, as_of=JAN):
    return Account(key, key, AccountKind.DEPOSIT, ownership, value(amount, as_of), access=access)


def debt(amount, rate, *, maturity=None):
    return Liability("loan", "Loan", LiabilityKind.INSTALLMENT_LOAN, SOLE,
                     value(amount), DebtTerms(RateKind.FIXED, D(rate), maturity))


def profile(*accounts, assets=(), liabilities=(), household=None):
    return FinancialProfile(
        Revision("profile", "1"), "USD",
        people=[Person("alex", "Alex"), Person("blair", "Blair"), Person("casey", "Casey")],
        accounts=accounts, assets=assets, liabilities=liabilities, household=household,
    )


def activity(key, kind, amount, *, source=None, destination=None, liability=None, subject=ALEX,
             start=JAN, end=None, frequency=Frequency.MONTHLY, split=None):
    return RecurringActivity(key, key, kind, subject, usd(amount), frequency, start, end,
                             source, destination, liability, split)


def payment(amount, *, split=None, key="pay", start=JAN, end=None):
    return activity(key, ActivityKind.DEBT_PAYMENT, amount, source="cash", liability="loan",
                    split=split, start=start, end=end)


def snapshot(records, *, months=1, subject=ALEX, activities=(), changes=(), rates=None, inflation=None,
             real=False, scenario=None, valuations=(), start=JAN, methodology=None, stochastic=None):
    if rates is None:
        rates = {item.id: "0" for item in records.positions_for(subject) if not isinstance(item, Liability)}
    request = AnalysisRequest(
        AnalysisType.MONTHLY_PROJECTION, MonthlyProjectionInputs(subject, start),
        methodology=methodology, stochastic=stochastic,
    )
    plan = FinancialPlan(
        Revision("plan", "1"), records.revision.id, activities=activities, changes=changes,
    )
    return resolve_analysis(
        request, profile=records, plan=plan, scenario=scenario,
        local=AnalysisOverrides(
            preferences=ModelPreferences(months, real),
            assumptions=EconomicAssumptions(annual_inflation=None if inflation is None else D(inflation)),
            position_valuations=valuations,
            position_growth=[PositionGrowth(key, D(rate)) for key, rate in rates.items()],
        ),
    )


def amounts(observation):
    return {position.position_id: position.amount for position in observation.positions}


class ProjectionReferenceTests(unittest.TestCase):
    def test_static_financial_positions_and_explicit_opening(self):
        car = Asset("car", "Car", AssetKind.VEHICLE, SOLE, value(3000))
        inputs = snapshot(profile(account("cash", 1000), assets=[car], liabilities=[debt(500, 0)]), months=2)
        result = project_monthly(inputs)
        self.assertEqual(result.methodology, METHODOLOGY)
        self.assertEqual(result.input_content_id, inputs.content_id)
        self.assertEqual(result.opening.as_of, JAN)
        self.assertEqual(result.opening.net_worth, D(3500))
        self.assertEqual(result.completed_months, 2)
        for result_month, start, end in zip(result.months, (JAN, FEB), (FEB, MAR)):
            self.assertEqual((result_month.period.start_on, result_month.period.end_before), (start, end))
            self.assertEqual(result_month.closing.as_of, end)
            self.assertEqual(result_month.closing.net_worth, D(3500))
            self.assertEqual(amounts(result_month.closing), {"cash": D(1000), "car": D(3000), "loan": D(500)})
            self.assertFalse(result_month.effects)

    def test_annual_returns_compound_to_reference_and_do_not_spread_to_cash(self):
        for rate, expected in (("0.12", "1120"), ("0", "1000"), ("-0.25", "750")):
            with self.subTest(rate=rate):
                car = Asset("car", "Car", AssetKind.VEHICLE, SOLE, value(1000))
                result = project_monthly(snapshot(
                    profile(account("invest", 1000), account("cash", 100), assets=[car]),
                    months=12, rates={"invest": rate, "cash": "0", "car": "-0.20"},
                ))
                close = amounts(result.months[-1].closing)
                self.assertAlmostEqual(close["invest"], D(expected), delta=D("0.0000001"))
                self.assertEqual(close["cash"], D(100))
                self.assertAlmostEqual(close["car"], D(800), delta=D("0.0000001"))
                self.assertTrue(any(effect.kind is EffectKind.ASSET_REVALUATION
                                    for effect in result.months[0].effects))

    def test_month_end_contributions_match_closed_form(self):
        contribution = activity("save", ActivityKind.CONTRIBUTION, 100, source="cash", destination="invest")
        result = project_monthly(snapshot(
            profile(account("cash", 10000), account("invest", 1000)),
            months=12, activities=[contribution], rates={"cash": "0", "invest": "0.10"},
        ))
        rate = math.pow(1.10, 1 / 12) - 1
        expected = 1000 * 1.10 + 100 * (1.10 - 1) / rate
        close = result.months[-1].closing
        self.assertAlmostEqual(float(amounts(close)["invest"]), expected, delta=1e-6)
        self.assertEqual(amounts(close)["cash"], D(8800))
        self.assertAlmostEqual(float(close.net_worth), 8800 + expected, delta=1e-6)
        self.assertEqual([item.kind for item in result.months[0].effects],
                         [EffectKind.ACCOUNT_RETURN, EffectKind.CONTRIBUTION])

    def test_income_expenses_and_scheduled_change_boundaries(self):
        pay = activity("pay", ActivityKind.EXTERNAL_INCOME, 100, destination="cash", end=APR)
        rent = activity("rent", ActivityKind.EXTERNAL_EXPENSE, 40, source="cash", start=FEB, end=MAR)
        change = ScheduledAmountChange("raise", "pay", FEB, usd(160))
        result = project_monthly(snapshot(
            profile(account("cash", 0)), months=4, activities=[rent, pay], changes=[change],
        ))
        self.assertEqual([month.closing.net_worth for month in result.months], [100, 220, 380, 380])
        self.assertEqual([month.reconciliation.economic_change for month in result.months], [100, 120, 160, 0])
        self.assertEqual([(effect.kind, effect.amount, effect.activity_id)
                          for effect in result.months[1].effects],
                         [(EffectKind.INCOME, 160, "pay"), (EffectKind.EXPENSE, 40, "rent")])

    def test_internal_movements_change_composition_and_post_both_sides(self):
        moves = [
            activity("transfer", ActivityKind.TRANSFER, 40, source="cash", destination="reserve"),
            activity("withdraw", ActivityKind.WITHDRAWAL, 25, source="invest", destination="cash"),
        ]
        result = project_monthly(snapshot(
            profile(account("cash", 100), account("reserve", 0), account("invest", 50)),
            activities=moves,
        ))
        month = result.months[0]
        self.assertEqual(amounts(month.closing), {"cash": 85, "reserve": 40, "invest": 25})
        self.assertEqual(month.closing.net_worth, 150)
        self.assertEqual(month.effects[0].postings, (Posting("cash", D(-40)), Posting("reserve", D(40))))
        self.assertEqual(month.effects[1].kind, EffectKind.WITHDRAWAL)
        self.assertEqual(month.reconciliation.economic_change, 0)

    def test_fixed_rate_debt_matches_independent_remaining_balance(self):
        result = project_monthly(snapshot(
            profile(account("cash", 10000), liabilities=[debt(12000, "0.06")]),
            months=6, activities=[payment("1032.80")],
        ))
        rate = D("0.005")
        growth = (1 + rate) ** 6
        expected_debt = D(12000) * growth - D("1032.80") * (growth - 1) / rate
        first = result.months[0]
        self.assertEqual(amounts(first.closing), {"cash": D("8967.20"), "loan": D("11027.20")})
        self.assertEqual([(effect.kind, effect.amount) for effect in first.effects], [
            (EffectKind.INTEREST_ACCRUED, D(60)), (EffectKind.INTEREST_PAID, D(60)),
            (EffectKind.PRINCIPAL_PAID, D("972.80")),
        ])
        self.assertEqual(first.closing.net_worth - result.opening.net_worth, D(-60))
        close = amounts(result.months[-1].closing)
        self.assertAlmostEqual(close["loan"], expected_debt, delta=D("0.00000005"))
        self.assertEqual(close["cash"], D("3803.20"))

    def test_payoff_caps_principal_and_stops_later_debits_and_interest(self):
        for loan, expected_first, expected_final in (
            (debt(150, 0), {"cash": 900, "loan": 50}, 850),
            (debt(100, "0.12", maturity=FEB), {"cash": 899, "loan": 0}, 899),
        ):
            with self.subTest(loan=loan):
                result = project_monthly(snapshot(
                    profile(account("cash", 1000), liabilities=[loan]), months=3,
                    activities=[payment(100 if loan.terms.annual_rate == 0 else 200)],
                ))
                self.assertEqual(amounts(result.months[0].closing), expected_first)
                self.assertEqual(amounts(result.months[-1].closing), {"cash": expected_final, "loan": 0})
                self.assertFalse(result.months[-1].effects)
                self.assertEqual(result.status, ProjectionStatus.COMPLETED)

    def test_inflation_is_reporting_only_and_uses_opening_dollars(self):
        records = profile(account("cash", 1200))
        inputs = snapshot(records, months=12, inflation="0.02", real=True)
        nominal = project_monthly(snapshot(records, months=12))
        result = project_monthly(inputs)
        self.assertEqual(result.opening.inflation_index, 1)
        self.assertEqual(result.opening.real_net_worth, 1200)
        self.assertAlmostEqual(result.months[-1].closing.inflation_index, D("1.02"), delta=D("1e-50"))
        self.assertEqual(result.months[-1].closing.real_net_worth, D("1176.47058824"))
        self.assertEqual([m.closing.net_worth for m in result.months], [m.closing.net_worth for m in nominal.months])
        self.assertEqual([m.reconciliation for m in result.months], [m.reconciliation for m in nominal.months])
        self.assertIsNone(nominal.months[-1].closing.real_net_worth)

    def test_scenario_uses_effective_opening_amount_contribution_and_return(self):
        records = profile(account("cash", 1000), account("invest", 100))
        save = activity("save", ActivityKind.CONTRIBUTION, 10, source="cash", destination="invest")
        baseline = snapshot(records, activities=[save])
        case = Scenario(Revision("case", "1"), "Alternative", "profile", overrides=AnalysisOverrides(
            activity_amounts=[ActivityAmountOverride("save", usd(20))],
            position_valuations=[PositionValuationOverride("invest", value(200))],
            position_growth=[PositionGrowth("invest", D("0.12")), PositionGrowth("cash", D(0))],
        ))
        changed = snapshot(records, scenario=case, rates={}, activities=[save])
        result = project_monthly(changed)
        self.assertEqual(amounts(project_monthly(baseline).months[0].closing), {"cash": 990, "invest": 110})
        self.assertEqual(amounts(result.opening), {"cash": 1000, "invest": 200})
        expected = 200 * math.pow(1.12, 1 / 12) + 20
        self.assertAlmostEqual(float(amounts(result.months[0].closing)["invest"]), expected, delta=1e-8)
        self.assertEqual(amounts(result.months[0].closing)["cash"], 980)
        self.assertEqual(records.accounts[-1].valuation.amount, 100)
        self.assertEqual(save.amount.amount, 10)
        self.assertEqual(baseline.opening_valuations()["invest"].amount, 100)
        sources = {origin.field: origin.source for origin in changed.origins}
        self.assertEqual(sources["assumptions.positions.invest.growth"].kind, SourceKind.SCENARIO_OVERRIDE)
        self.assertEqual(project_monthly(ResolvedAnalysis.from_json(changed.to_json())), result)


class ProjectionBoundaryTests(unittest.TestCase):
    def assert_readiness_issue(self, inputs, code):
        with self.assertRaises(ProjectionReadinessError) as raised:
            project_monthly(inputs)
        self.assertIn(code, [issue.code for issue in raised.exception.issues])

    def test_fully_covered_joint_position_once_and_partial_ownership_rejected(self):
        household = Household("house", "House", ["alex", "blair"])
        joint = Ownership([Owner("alex"), Owner("blair")])
        records = profile(account("joint", 300, ownership=joint), household=household)
        result = project_monthly(snapshot(records, subject=HOUSE))
        self.assertEqual(result.opening.net_worth, 300)
        self.assertEqual(len(result.months[0].closing.positions), 1)
        self.assert_readiness_issue(snapshot(records), "partial_ownership")
        mixed = Ownership([Owner("alex", D("0.5")), Owner("casey", D("0.5"))])
        records = profile(account("joint", 300, ownership=mixed), household=household)
        self.assert_readiness_issue(snapshot(records, subject=HOUSE), "partial_ownership")

    def test_outside_subject_activity_affecting_individual_is_not_silently_omitted(self):
        records = profile(account("cash", 10), household=Household("house", "House", ["alex", "blair"]))
        household_expense = activity("rent", ActivityKind.EXTERNAL_EXPENSE, 2, source="cash", subject=HOUSE)
        self.assert_readiness_issue(snapshot(records, activities=[household_expense]), "out_of_scope_activity")
        result = project_monthly(snapshot(records, activities=[household_expense], subject=HOUSE))
        self.assertEqual(result.months[0].closing.net_worth, 8)
        future = replace(household_expense, start_on=FEB)
        self.assertEqual(project_monthly(snapshot(records, activities=[future])).months[0].closing.net_worth, 10)

    def test_invalid_readiness_inputs(self):
        records = profile(account("cash", 10), account("locked", 10, access=Access.LOCKED))
        withdraw = activity("move", ActivityKind.WITHDRAWAL, 1, source="locked", destination="cash")
        pay = activity("salary", ActivityKind.EXTERNAL_INCOME, 2, destination="cash")
        expense = activity("rent", ActivityKind.EXTERNAL_EXPENSE, 1)
        cases = [
            (snapshot(records, rates={}), "missing_growth"),
            (snapshot(records, stochastic=StochasticExecution(0, 10)), "stochastic"),
            (snapshot(records, methodology=Revision(METHODOLOGY.id, "0")), "methodology"),
            (snapshot(records, months=200000), "horizon"),
            (snapshot(records, activities=[withdraw]), "restricted_funding"),
            (snapshot(records, activities=[replace(pay, to_account_id=None)]), "missing_destination"),
            (snapshot(records, activities=[expense]), "missing_funding_account"),
            (snapshot(records, activities=[replace(pay, frequency=Frequency.WEEKLY)]), "unsupported_schedule"),
            (snapshot(records, activities=[replace(pay, start_on=date(2030, 1, 2))]), "unsupported_schedule"),
            (snapshot(records, activities=[pay], changes=[
                ScheduledAmountChange("midmonth", "salary", date(2030, 1, 10), usd(10))
            ]), "unsupported_change_date"),
            (resolve_analysis(AnalysisRequest(AnalysisType.LOAN_PAYMENT, LoanPaymentInputs(usd(1), D(0), 1))),
             "analysis_type"),
        ]
        for inputs, code in cases:
            with self.subTest(code=code):
                self.assert_readiness_issue(inputs, code)
        ready = snapshot(records, methodology=METHODOLOGY)
        self.assertEqual(project_monthly(ready).methodology, METHODOLOGY)

    def test_valuations_must_be_aligned_and_empty_scope_is_valid(self):
        records = profile(account("cash", 10, as_of=date(2029, 12, 1)))
        self.assert_readiness_issue(snapshot(records), "unaligned_valuation")
        aligned = snapshot(records, valuations=[PositionValuationOverride("cash", value(0))])
        self.assertEqual(project_monthly(aligned).opening.net_worth, 0)
        result = project_monthly(snapshot(profile(), months=2))
        self.assertEqual(result.opening.positions, ())
        self.assertEqual(result.months[-1].closing.net_worth, 0)

    def test_unrestricted_brokerage_requires_explicit_cash_to_fund_withdrawals(self):
        brokerage = replace(account("brokerage", 100), kind=AccountKind.BROKERAGE)
        withdrawal = activity("withdraw", ActivityKind.WITHDRAWAL, 50, source="brokerage", destination="cash")
        for holding in (None, Holding("equity", AssetClass.EQUITY, weight=D(1)),
                        Holding("partial-cash", AssetClass.CASH, weight=D("0.75"))):
            positions = profile(account("cash", 0), replace(brokerage, holdings=[] if holding is None else [holding]))
            self.assert_readiness_issue(snapshot(positions, activities=[withdrawal]), "noncash_funding")
        all_cash = replace(brokerage, holdings=[Holding("cash-holding", AssetClass.CASH, value=usd(100))])
        positions = profile(account("cash", 0), all_cash)
        result = project_monthly(snapshot(positions, activities=[withdrawal]))
        self.assertEqual(amounts(result.months[0].closing), {"brokerage": 50, "cash": 50})
        increased = PositionValuationOverride("brokerage", value(150))
        self.assert_readiness_issue(
            snapshot(positions, activities=[withdrawal], valuations=[increased]), "noncash_funding",
        )

    def test_debt_structure_and_dynamic_limits(self):
        loan = debt(100, "0.12")
        for bad in (replace(loan, terms=None), replace(loan, kind=LiabilityKind.REVOLVING),
                    replace(loan, terms=DebtTerms(RateKind.VARIABLE, D("0.12"))),
                    replace(loan, terms=DebtTerms(RateKind.FIXED))):
            with self.subTest(bad=bad):
                self.assert_readiness_issue(snapshot(profile(account("cash", 100), liabilities=[bad])),
                                            "unsupported_debt")
        midmonth = debt(100, "0.12", maturity=date(2030, 1, 15))
        self.assert_readiness_issue(snapshot(profile(account("cash", 100), liabilities=[midmonth])),
                                    "unsupported_maturity")
        records = profile(account("cash", 300), liabilities=[loan])
        self.assert_readiness_issue(snapshot(records, activities=[payment(20), payment(30, key="second")]),
                                    "competing_debt_payments")
        for debt_position, activities, code in (
            (loan, [], "missing_debt_payment"),
            (loan, [payment("0.50")], "payment_below_interest"),
            (debt(100, "0.12", maturity=FEB), [payment(50)], "maturity_balance"),
            (loan, [payment(50, split=DebtPaymentSplit(usd(50), usd(0)))], "payment_split_mismatch"),
        ):
            with self.subTest(code=code):
                result = project_monthly(snapshot(profile(account("cash", 300), liabilities=[debt_position]),
                                                  activities=activities))
                self.assertEqual(result.status, ProjectionStatus.STOPPED)
                self.assertEqual(result.completed_months, 0)
                self.assertEqual(result.termination.issues[0].code, code)
                self.assertEqual(amounts(result.opening), {"cash": 300, "loan": 100})
        fixed_split = payment(50, split=DebtPaymentSplit(usd(49), usd(1)))
        result = project_monthly(snapshot(records, months=2, activities=[fixed_split]))
        self.assertEqual(result.completed_months, 1)
        self.assertEqual(result.termination.issues[0].code, "payment_split_mismatch")

    def test_grouped_shortfall_preserves_last_state_and_exposes_unfunded_debits(self):
        records = profile(account("cash", 100), account("other", 1000))
        expenses = [
            activity("rent", ActivityKind.EXTERNAL_EXPENSE, 50, source="cash"),
            activity("bill", ActivityKind.EXTERNAL_EXPENSE, 30, source="cash", start=FEB),
        ]
        result = project_monthly(snapshot(records, months=3, activities=expenses))
        self.assertEqual(result.status, ProjectionStatus.STOPPED)
        self.assertEqual(result.completed_months, 1)
        self.assertEqual(result.requested_months, 3)
        self.assertEqual(amounts(result.months[-1].closing), {"cash": 50, "other": 1000})
        stop = result.termination
        self.assertEqual(stop.period.start_on, FEB)
        shortfall = stop.shortfalls[0]
        self.assertEqual((shortfall.account_id, shortfall.available, shortfall.required, shortfall.unfunded),
                         ("cash", 50, 80, 30))
        self.assertEqual({item.activity_id: item.amount for item in shortfall.debits}, {"rent": 50, "bill": 30})

    def test_internal_receipts_cannot_fund_same_month_and_debt_shortfall_is_atomic(self):
        records = profile(account("cash", 100), account("reserve", 0))
        move = activity("move", ActivityKind.TRANSFER, 50, source="cash", destination="reserve")
        bill = activity("bill", ActivityKind.EXTERNAL_EXPENSE, 50, source="reserve")
        result = project_monthly(snapshot(records, activities=[move, bill]))
        self.assertEqual(result.completed_months, 0)
        self.assertEqual(result.termination.shortfalls[0].account_id, "reserve")
        self.assertEqual(result.termination.shortfalls[0].unfunded, 50)
        result = project_monthly(snapshot(profile(account("cash", 0), liabilities=[debt(100, "0.12")]),
                                          activities=[payment(10)]))
        self.assertEqual(result.completed_months, 0)
        self.assertEqual(result.termination.shortfalls[0].unfunded, 10)
        self.assertEqual(amounts(result.opening)["loan"], 100)

    def test_position_specific_growth_validation_and_precedence(self):
        records = profile(account("cash", 100), liabilities=[debt(0, 0)])
        case = Scenario(Revision("case", "1"), "Case", "profile",
                        overrides=AnalysisOverrides(position_growth=[PositionGrowth("cash", D("0.1"))]))
        self.assertEqual(project_monthly(snapshot(records, scenario=case)).months[0].closing.net_worth, 100)
        with self.assertRaisesRegex(ValueError, "in-scope account or asset"):
            snapshot(records, rates={"cash": "0", "loan": "0"})
        with self.assertRaisesRegex(ValueError, "greater than -1"):
            snapshot(records, rates={"cash": "-1"})

    def test_deterministic_serialization_long_horizon_and_half_even_rounding(self):
        records = profile(account("cash", 1000), account("reserve", 2))
        a = activity("pay", ActivityKind.EXTERNAL_INCOME, 1, destination="reserve")
        b = activity("bill", ActivityKind.EXTERNAL_EXPENSE, 1, source="reserve")
        rates = {"cash": "0.07", "reserve": "0"}
        inputs = snapshot(records, months=360, rates=rates, activities=[a, b])
        result = project_monthly(inputs)
        with localcontext(prec=5):
            reordered = snapshot(replace(records, accounts=list(reversed(records.accounts))),
                                 months=360, rates=dict(reversed(tuple(rates.items()))), activities=[b, a])
            self.assertEqual(project_monthly(reordered).to_json(), result.to_json())
        expected = D(1000) * D("1.07") ** 30
        self.assertAlmostEqual(amounts(result.months[-1].closing)["cash"], expected, delta=D("0.00001"))
        self.assertTrue(all(m.reconciliation.net_worth_residual == 0 for m in result.months))
        self.assertTrue(all(m.reconciliation.max_absolute_position_residual == 0 for m in result.months))
        wire = json.loads(result.to_json())
        self.assertEqual(wire["schema_version"], 1)
        self.assertEqual(wire["opening"]["net_worth"], "1002")
        tiny = project_monthly(snapshot(profile(account("cash", 0), liabilities=[debt("0.000006", "0.01")])))
        self.assertEqual(tiny.status, ProjectionStatus.COMPLETED)
        self.assertFalse(tiny.months[0].effects)  # exact half a quantum rounds to even zero

    def test_reconciliation_detects_offsetting_position_errors_and_economic_errors(self):
        opening = {"a": D(100), "b": D(200)}
        kinds = {"a": PositionKind.ACCOUNT, "b": PositionKind.ACCOUNT}
        transfer = FinancialEffect(EffectKind.TRANSFER, D(20), (Posting("a", D(-20)), Posting("b", D(20))))
        with self.assertRaisesRegex(ReconciliationError, "position postings"):
            reconcile(opening, {"a": D(90), "b": D(210)}, kinds, (transfer,))
        phantom = FinancialEffect(EffectKind.TRANSFER, D(20), (Posting("a", D(-20)), Posting("b", D(30))))
        with self.assertRaisesRegex(ReconciliationError, "net worth"):
            reconcile(opening, {"a": D(80), "b": D(230)}, kinds, (phantom,))

    def test_projection_runs_without_application_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent("""
            import sys
            sys.path[:0] = sys.argv[1:]
            from test_monthly_projection import profile, account, snapshot, project_monthly

            result = project_monthly(snapshot(profile(account("cash", 100))))
            assert result.months[0].closing.net_worth == 100
        """)
        run = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(root), str(root / "tests")],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
