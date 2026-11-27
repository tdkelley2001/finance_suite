"""Synthetic examples and invariant tests for the canonical domain."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal as D, localcontext
import unittest

from moneylab.domain.planning import (
    ActivityKind, DebtPaymentSplit, FinancialPlan, Frequency, Goal, RecurringActivity,
    ScheduledAmountChange,
)
from moneylab.domain.profile import (
    Access, Account, AccountKind, Asset, AssetClass, AssetKind, DebtTerms,
    FinancialProfile, Holding, Household, Liability, LiabilityKind, Owner, Ownership,
    Person, RateKind, Subject, SubjectKind, TaxTreatment,
)
from moneylab.domain.values import Money, Revision, Source, SourceKind, Valuation


START = date(2030, 1, 1)
INDIVIDUAL = Subject(SubjectKind.PERSON, "alex")
HOUSEHOLD = Subject(SubjectKind.HOUSEHOLD, "household")


def usd(amount):
    return Money(D(amount), "USD")


def individual_example():
    owner = Ownership([Owner("alex")])
    profile = FinancialProfile(
        Revision("profile", "1"), "USD", people=[Person("alex", "Alex", date(1990, 4, 20))],
        accounts=[
            Account("cash", "Checking", AccountKind.DEPOSIT, owner,
                    Valuation("USD", D("5000"), START), access=Access.UNRESTRICTED),
            Account("ira", "Roth IRA", AccountKind.INDIVIDUAL_RETIREMENT, owner,
                    Valuation("USD", D("12000"), START), TaxTreatment.ROTH, Access.CONDITIONAL,
                    holdings=[Holding("equity", AssetClass.EQUITY, weight=D("0.8"))]),
        ],
        assets=[Asset("car", "Car", AssetKind.VEHICLE, owner, Valuation("USD", D("8000"), START))],
        liabilities=[
            Liability("loan", "Car loan", LiabilityKind.INSTALLMENT_LOAN, owner,
                      Valuation("USD", D("6000"), START),
                      DebtTerms(RateKind.FIXED, D("0.06"), date(2033, 1, 1))),
        ],
    )
    plan = FinancialPlan(
        Revision("plan", "1"),
        profile.revision.id,
        activities=[
            RecurringActivity("pay", "Pay", ActivityKind.EXTERNAL_INCOME, INDIVIDUAL,
                              usd("4000"), Frequency.MONTHLY, START, to_account_id="cash"),
            RecurringActivity("rent", "Rent", ActivityKind.EXTERNAL_EXPENSE, INDIVIDUAL,
                              usd("1500"), Frequency.MONTHLY, START, from_account_id="cash"),
            RecurringActivity("save", "IRA savings", ActivityKind.CONTRIBUTION, INDIVIDUAL,
                              usd("300"), Frequency.MONTHLY, START,
                              from_account_id="cash", to_account_id="ira"),
            RecurringActivity("debt", "Car loan payment", ActivityKind.DEBT_PAYMENT, INDIVIDUAL,
                              usd("200"), Frequency.MONTHLY, START, from_account_id="cash",
                              liability_id="loan", debt_split=DebtPaymentSplit(usd("170"), usd("30"))),
        ],
        goals=[Goal("reserves", "Emergency reserves", INDIVIDUAL, usd("9000"), date(2031, 1, 1),
                    funding_account_ids=["cash"])],
        changes=[ScheduledAmountChange("raise", "pay", date(2030, 7, 1), usd("4200"))],
    )
    return profile, plan


def household_example():
    profile, plan = individual_example()
    people = (*profile.people, Person("blair", "Blair"), Person("lee", "Lee"))
    household = Household("household", "Example household", ["blair", "alex"])
    joint = Account(
        "joint", "Shared checking", AccountKind.DEPOSIT,
        Ownership([Owner("alex", D("0.6")), Owner("blair", D("0.4"))]),
        Valuation("USD", D("10000"), START), beneficiary_ids=["lee"],
    )
    blair_cash = Account(
        "blair-cash", "Checking", AccountKind.DEPOSIT, Ownership([Owner("blair")]),
        Valuation("USD", D("2000"), START),
    )
    return replace(profile, people=people, household=household,
                   accounts=(*profile.accounts, joint, blair_cash)), plan


class FinancialDomainTests(unittest.TestCase):
    def test_individual_position_and_financial_plan_are_separate(self):
        profile, plan = individual_example()
        plan.validate_against(profile)
        self.assertEqual(len(profile.positions_for(INDIVIDUAL)), 4)
        self.assertEqual(profile.accounts[0].valuation.amount, D("5000"))
        self.assertEqual(profile.accounts[1].tax_treatment, TaxTreatment.ROTH)
        self.assertEqual(profile.accounts[1].access, Access.CONDITIONAL)
        activity = {item.id: item for item in plan.activities}
        self.assertEqual(activity["save"].kind, ActivityKind.CONTRIBUTION)
        self.assertEqual(activity["debt"].debt_split.interest, usd("30"))
        self.assertEqual(plan.changes[0].new_amount, usd("4200"))
        self.assertEqual(plan.goals[0].funding_account_ids, ("cash",))
        self.assertFalse(hasattr(profile, "net_worth"))
        self.assertFalse(hasattr(profile, "activities"))

    def test_joint_records_appear_once_and_membership_does_not_make_an_owner(self):
        profile, plan = household_example()
        plan.validate_against(profile)
        positions = profile.positions_for(HOUSEHOLD)
        self.assertEqual(len(positions), 6)
        joint = next(record for record in positions if record.id == "joint")
        self.assertEqual(sum(record.id == joint.id for record in positions), 1)
        self.assertEqual(joint.ownership.share_within(profile.people_in(HOUSEHOLD)), D(1))
        self.assertEqual(joint.ownership.share_within(profile.people_in(INDIVIDUAL)), D("0.6"))
        beneficiary = Subject(SubjectKind.PERSON, "lee")
        self.assertEqual(profile.positions_for(beneficiary), ())
        self.assertEqual(plan.activities_for(profile, HOUSEHOLD), plan.activities)
        renamed = replace(profile, people=[replace(person, name="Renamed") for person in profile.people])
        self.assertEqual(renamed.positions_for(HOUSEHOLD), positions)

    def test_unspecified_joint_shares_are_not_inferred(self):
        joint = Ownership([Owner("alex"), Owner("outside")])
        self.assertIsNone(joint.share_within(frozenset({"alex"})))
        self.assertEqual(joint.share_within(frozenset({"alex", "outside"})), D(1))
        self.assertEqual(joint.share_within(frozenset({"other"})), D(0))
        for owners in (
            [], [Owner("alex"), Owner("alex")], [Owner("alex", D("0.9"))],
            [Owner("alex"), Owner("outside", D("0.5"))],
        ):
            with self.subTest(owners=owners), self.assertRaises(ValueError):
                Ownership(owners)

    def test_profile_rejects_invalid_relationships_and_duplicate_entities(self):
        profile, _ = household_example()
        first = profile.accounts[0]
        for changes, message in (
            ({"accounts": [first, first]}, "duplicate Account"),
            ({"assets": [replace(profile.assets[0], id=first.id)]}, "unique across kinds"),
            ({"accounts": [replace(first, ownership=Ownership([Owner("unknown")]))]}, "owner"),
            ({"accounts": [replace(first, beneficiary_ids=["unknown"])]}, "beneficiary"),
            ({"household": Household("household", "Example", ["unknown"])}, "unknown people"),
            ({"people": [profile.people[0], profile.people[0]]}, "duplicate Person"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                replace(profile, **changes)
        # Nonmembers can participate in a legal relationship without joining the household.
        outside_owner = replace(first, ownership=Ownership([Owner("alex"), Owner("lee")]))
        amended = replace(profile, accounts=[outside_owner])
        self.assertIn(outside_owner, amended.positions_for(HOUSEHOLD))
        self.assertIsNone(outside_owner.ownership.share_within(amended.people_in(HOUSEHOLD)))

    def test_money_and_valuations_validate_currency_precision_and_unknowns(self):
        self.assertIsNone(Valuation("USD").amount)
        self.assertEqual(Valuation("USD", D(0), START).amount, D(0))
        for value in (float("nan"), float("inf"), 1.1, D("NaN"), D("Infinity"),
                      D("0.000000001"), D("1000000000000000000")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Money(value, "USD")
        for amount, as_of in ((D(0), None), (D(-1), START), (D(0), datetime(2030, 1, 1))):
            with self.subTest(amount=amount, as_of=as_of), self.assertRaises(ValueError):
                Valuation("USD", amount, as_of)
        with self.assertRaises(ValueError):
            Money(D(10), "usd")
        profile, _ = individual_example()
        with self.assertRaisesRegex(ValueError, "profile currency"):
            replace(profile, accounts=[replace(profile.accounts[0], valuation=Valuation("EUR"))])

    def test_holdings_leave_unclassified_residual_and_reject_inconsistency(self):
        profile, _ = individual_example()
        account = profile.accounts[0]
        asset = Holding("a", AssetClass.EQUITY, security_id="SYNTHETIC", value=usd("4000"))
        cash = Holding("c", AssetClass.CASH, value=usd("500"))
        disclosed = replace(account, holdings=[asset, cash])
        self.assertEqual(disclosed.valuation.amount, D("5000"))
        self.assertEqual(sum(item.value.amount for item in disclosed.holdings), D("4500"))
        w1 = Holding("w1", AssetClass.EQUITY, weight=D("0.8"))
        w2 = Holding("w2", AssetClass.FIXED_INCOME, weight=D("0.20000001"))
        with localcontext(prec=2), self.assertRaisesRegex(ValueError, "weights exceed"):
            replace(account, holdings=[w1, w2])
        for holdings, message in (
            ([asset, asset], "duplicate"), ([w1, cash], "single basis"),
            ([replace(asset, value=usd("5000.01"))], "exceed account"),
            ([replace(asset, value=Money(D(2), "EUR"))], "expected USD"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                replace(account, holdings=holdings)
        self.assertEqual(replace(account, valuation=Valuation("USD"), holdings=[w1]).holdings, (w1,))
        with self.assertRaisesRegex(ValueError, "known account value"):
            replace(account, valuation=Valuation("USD"), holdings=[asset])

    def test_plans_validate_routes_splits_and_references(self):
        profile, plan = individual_example()
        activities = {item.id: item for item in plan.activities}
        with self.assertRaisesRegex(ValueError, "plan requires profile"):
            plan.validate_against(replace(profile, revision=Revision("wrong", "1")))
        with self.assertRaisesRegex(ValueError, "distinct accounts"):
            replace(activities["save"], to_account_id="cash")
        with self.assertRaisesRegex(ValueError, "external income"):
            replace(activities["pay"], from_account_id="ira")
        with self.assertRaisesRegex(ValueError, "must equal principal plus interest"):
            replace(activities["debt"], amount=usd("210"))
        self.assertIsNone(replace(activities["debt"], debt_split=None).debt_split)
        with self.assertRaisesRegex(ValueError, "unknown or out-of-scope account"):
            replace(plan, activities=[replace(activities["rent"], from_account_id="unknown")],
                    changes=[]).validate_against(profile)
        with self.assertRaisesRegex(ValueError, "out-of-scope account"):
            household, _ = household_example()
            replace(plan, activities=[replace(activities["rent"], from_account_id="blair-cash")],
                    changes=[]).validate_against(household)
        with self.assertRaisesRegex(ValueError, "unknown or out-of-scope liability"):
            replace(plan, activities=[replace(activities["debt"], liability_id="unknown")],
                    changes=[]).validate_against(profile)
        with self.assertRaisesRegex(ValueError, "funding account"):
            replace(plan, goals=[replace(plan.goals[0], funding_account_ids=["loan"])]).validate_against(profile)

    def test_period_boundaries_and_scheduled_changes(self):
        _, plan = individual_example()
        pay = next(item for item in plan.activities if item.id == "pay")
        change = plan.changes[0]
        with self.assertRaisesRegex(ValueError, "end must follow"):
            replace(pay, end_before=START)
        with self.assertRaisesRegex(ValueError, "within the activity period"):
            replace(plan, activities=[replace(pay, end_before=change.effective_on)])
        with self.assertRaisesRegex(ValueError, "existing income or expense"):
            replace(plan, changes=[replace(change, activity_id="save")])
        with self.assertRaisesRegex(ValueError, "only one change"):
            replace(plan, changes=[change, replace(change, id="another")])
        with self.assertRaisesRegex(ValueError, "expected USD"):
            replace(plan, changes=[replace(change, new_amount=Money(D(42), "EUR"))])

    def test_external_provenance_can_be_recorded_on_a_fact(self):
        source = Source(SourceKind.EXTERNAL_DATA, Revision("synthetic-statement", "1"))
        profile, plan = individual_example()
        self.assertEqual(replace(profile.accounts[0], source=source).source, source)
        self.assertEqual(replace(plan.activities[0], source=source).source, source)
        with self.assertRaisesRegex(ValueError, "user_fact"):
            Person("alex", "Alex", source=Source(SourceKind.SCENARIO_OVERRIDE))
