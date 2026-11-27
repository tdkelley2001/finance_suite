"""Examples and invariants for resolution and reproducible analysis inputs."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal as D
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

from moneylab.configuration.models import (
    ActivityAmountOverride, AnalysisOverrides, AnalysisRequest, AnalysisType,
    EconomicAssumptions, LoanPaymentInputs, ModelPreferences, MonthlyProjectionInputs,
    PositionValuationOverride, Preset, ResearchDefaults, Scenario, StochasticExecution,
)
from moneylab.configuration.resolve import resolve_analysis
from moneylab.configuration.snapshot import MissingAnalysisInput, ResolvedAnalysis
from moneylab.domain.profile import AssetClass, FinancialProfile, Holding
from moneylab.domain.values import Money, Revision, Source, SourceKind, Valuation

from test_canonical_domain import HOUSEHOLD, INDIVIDUAL, START, household_example, individual_example, usd


def projection_request(subject=INDIVIDUAL, **metadata):
    return AnalysisRequest(
        AnalysisType.MONTHLY_PROJECTION, MonthlyProjectionInputs(subject, START), **metadata,
    )


def research_defaults():
    # Synthetic values for validation only.
    return ResearchDefaults(
        Revision("illustrative-defaults", "1"),
        EconomicAssumptions(annual_inflation=D("0.02"), annual_investment_return=D("0.04")),
        ModelPreferences(horizon_months=24, use_real_dollars=True),
    )


def illustrative_preset():
    return Preset(
        Revision("illustrative-preset", "2"), "Illustrative",
        EconomicAssumptions(annual_investment_return=D("0.05")),
        ModelPreferences(horizon_months=36),
    )


def amount_for(plan, activity_id):
    return next(activity.amount for activity in plan.activities if activity.id == activity_id)


class ResolutionTests(unittest.TestCase):
    def test_standalone_loan_snapshot_and_primitive(self):
        from moneylab.engine.calculations import fixed_payment

        request = AnalysisRequest(AnalysisType.LOAN_PAYMENT, LoanPaymentInputs(usd("1200"), D(0), 12))
        snapshot = resolve_analysis(request)
        self.assertIsNone(snapshot.profile)
        self.assertIsNone(snapshot.plan)
        inputs = snapshot.request.inputs
        # This example has an exact whole-year term for the tested primitive.
        years, remainder = divmod(inputs.term_months, 12)
        self.assertEqual(remainder, 0)
        payment = fixed_payment(float(inputs.principal.amount), float(inputs.annual_rate), years)
        self.assertEqual(payment, 100)
        self.assertEqual(ResolvedAnalysis.from_json(snapshot.to_json()), snapshot)
        uneven_term = replace(request, inputs=replace(inputs, term_months=13))
        self.assertEqual(resolve_analysis(uneven_term).request.inputs.term_months, 13)
        with self.assertRaisesRegex(ValueError, "standalone loan"):
            resolve_analysis(request, preset=illustrative_preset())

    def test_scenario_comparison_and_configuration_precedence(self):
        profile, plan = household_example()
        preset = illustrative_preset()
        defaults = research_defaults()
        baseline = Scenario(Revision("baseline", "1"), "Baseline", "profile", "plan", preset.revision.id)
        alternative = Scenario(
            Revision("alternative", "1"), "Higher savings", "profile", "plan", preset.revision.id,
            AnalysisOverrides(
                EconomicAssumptions(annual_investment_return=D("0.03")),
                activity_amounts=[ActivityAmountOverride("save", usd("500"))],
            ),
        )
        local = AnalysisOverrides(
            EconomicAssumptions(annual_investment_return=D(0)),
            ModelPreferences(use_real_dollars=False),
            [ActivityAmountOverride("save", usd(0))],
        )
        context = dict(profile=profile, plan=plan, preset=preset, defaults=defaults)
        request = projection_request(HOUSEHOLD)
        snapshot_a = resolve_analysis(request, scenario=baseline, **context)
        snapshot_b = resolve_analysis(request, scenario=alternative, **context)
        snapshot_local = resolve_analysis(request, scenario=alternative, local=local, **context)

        for snapshot, amount, annual_return, expected_source in (
            (snapshot_a, "300", "0.05", SourceKind.PRESET),
            (snapshot_b, "500", "0.03", SourceKind.SCENARIO_OVERRIDE),
            (snapshot_local, "0", "0", SourceKind.LOCAL_OVERRIDE),
        ):
            self.assertEqual(amount_for(snapshot.plan, "save"), usd(amount))
            self.assertEqual(snapshot.assumptions.annual_investment_return, D(annual_return))
            self.assertEqual(snapshot.assumptions.annual_inflation, D("0.02"))
            self.assertEqual(snapshot.preferences.horizon_months, 36)
            origins = {item.field: item.source for item in snapshot.origins}
            self.assertEqual(origins["assumptions.annual_investment_return"].kind, expected_source)
            self.assertEqual(origins["assumptions.annual_inflation"].reference, defaults.revision)
            self.assertEqual(origins["profile"], Source(SourceKind.USER_FACT, profile.revision))

        self.assertFalse(snapshot_local.preferences.use_real_dollars)
        self.assertTrue(snapshot_b.preferences.use_real_dollars)
        origins = {item.field: item.source for item in snapshot_b.origins}
        self.assertEqual(origins["plan.activities.save.amount"],
                         Source(SourceKind.SCENARIO_OVERRIDE, alternative.revision))
        self.assertEqual(origins["plan.activities.pay.amount"], Source(SourceKind.USER_PLAN, plan.revision))
        self.assertEqual(snapshot_b.scenario_revision, alternative.revision)
        self.assertEqual(snapshot_b.preset_revision, preset.revision)
        self.assertEqual(amount_for(plan, "save"), usd("300"))
        self.assertEqual(alternative.overrides.activity_amounts[0].amount, usd("500"))
        self.assertEqual(preset.assumptions.annual_investment_return, D("0.05"))
        self.assertEqual(resolve_analysis(request, scenario=baseline, **context), snapshot_a)

    def test_missing_projection_inputs_are_reported_separately_from_structural_validity(self):
        profile = FinancialProfile(Revision("partial", "1"), "USD", people=individual_example()[0].people)
        with self.assertRaisesRegex(MissingAnalysisInput, "requires a financial profile"):
            resolve_analysis(projection_request(), preset=illustrative_preset())
        with self.assertRaisesRegex(MissingAnalysisInput, "requires a horizon"):
            resolve_analysis(projection_request(), profile=profile)
        result = resolve_analysis(projection_request(), profile=profile, preset=illustrative_preset())
        self.assertIsNone(result.assumptions.annual_inflation)
        self.assertIsNone(result.preferences.use_real_dollars)
        self.assertEqual(result.profile.accounts, ())
        with self.assertRaisesRegex(MissingAnalysisInput, "requires an inflation assumption"):
            resolve_analysis(projection_request(), profile=profile, preset=illustrative_preset(),
                             local=AnalysisOverrides(preferences=ModelPreferences(use_real_dollars=True)))
        with self.assertRaisesRegex(ValueError, "unknown analysis subject"):
            resolve_analysis(projection_request(HOUSEHOLD), profile=profile, defaults=research_defaults())

        full, _ = individual_example()
        account = full.accounts[0]
        for valuation, error, message in (
            (Valuation("USD"), MissingAnalysisInput, "requires an opening amount"),
            (Valuation("USD", D(0), date(2030, 2, 1)), ValueError, "dated after"),
        ):
            partial = replace(full, accounts=[replace(account, valuation=valuation)])
            with self.subTest(message=message), self.assertRaisesRegex(error, message):
                resolve_analysis(projection_request(), profile=partial, defaults=research_defaults())
        zero = replace(full, accounts=[replace(account, valuation=Valuation("USD", D(0), START))])
        result = resolve_analysis(projection_request(), profile=zero, defaults=research_defaults())
        self.assertEqual(result.profile.accounts[0].valuation.amount, D(0))

    def test_unauthorized_overrides_and_invalid_configuration(self):
        profile, plan = household_example()
        defaults = research_defaults()
        for amounts, message in (
            ([ActivityAmountOverride("unknown", usd(100))], "ineligible"),
            ([ActivityAmountOverride("debt", usd(100))], "ineligible"),
            ([ActivityAmountOverride("save", Money(D(100), "EUR"))], "expected USD"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                resolve_analysis(projection_request(), profile=profile, plan=plan, defaults=defaults,
                                 local=AnalysisOverrides(activity_amounts=amounts))
        with self.assertRaises(TypeError):
            AnalysisOverrides(account_balance=usd(0))
        with self.assertRaisesRegex(ValueError, "typed assumptions"):
            replace(illustrative_preset(), assumptions={"accounts": []})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            AnalysisOverrides(activity_amounts=[ActivityAmountOverride("save", usd(0))] * 2)
        with self.assertRaisesRegex(ValueError, "greater than -1"):
            EconomicAssumptions(annual_inflation=D("-1"))
        with self.assertRaises(ValueError):
            ModelPreferences(horizon_months=True)
        with self.assertRaises(ValueError):
            ModelPreferences(use_real_dollars=0)

    def test_invalid_scenario_references_and_out_of_scope_activity(self):
        profile, plan = household_example()
        scenario = Scenario(Revision("case", "1"), "Case", "profile", "plan", "illustrative-preset")
        context = dict(profile=profile, plan=plan, preset=illustrative_preset())
        for broken, message in (
            (replace(scenario, profile_id="wrong"), "requires profile"),
            (replace(scenario, plan_id="wrong"), "requires plan"),
            (replace(scenario, preset_id="wrong"), "requires preset"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                resolve_analysis(projection_request(), scenario=broken, **context)
        to_household = replace(plan.activities[0], subject=HOUSEHOLD)
        other_plan = replace(plan, activities=[to_household], changes=[])
        with self.assertRaisesRegex(ValueError, "ineligible"):
            resolve_analysis(
                projection_request(), profile=profile, plan=other_plan, defaults=research_defaults(),
                local=AnalysisOverrides(activity_amounts=[ActivityAmountOverride(to_household.id, usd(50))]),
            )

    def test_null_falls_through_and_shadowed_overrides_remain_validated(self):
        profile, plan = individual_example()
        preset = illustrative_preset()
        request = projection_request()
        case = Scenario(
            Revision("case", "1"), "Case", profile.revision.id,
            overrides=AnalysisOverrides(
                assumptions=EconomicAssumptions(annual_investment_return=D("0.08")),
            ),
        )
        result = resolve_analysis(
            request, profile=profile, plan=plan, preset=preset, scenario=case,
            local=AnalysisOverrides(assumptions=EconomicAssumptions(annual_investment_return=None)),
        )
        self.assertEqual(result.assumptions.annual_investment_return, D("0.08"))

        bad_override = ActivityAmountOverride("save", Money(D(50), "EUR"))
        bad = replace(case, overrides=AnalysisOverrides(activity_amounts=[bad_override]))
        with self.assertRaisesRegex(ValueError, "expected USD"):
            resolve_analysis(
                request, profile=profile, plan=plan, preset=preset, scenario=bad,
                local=AnalysisOverrides(activity_amounts=[ActivityAmountOverride("save", usd(25))]),
            )


class PositionOverrideTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.plan = household_example()
        self.context = dict(profile=self.profile, plan=self.plan, preset=illustrative_preset())
        self.request = projection_request()

    @staticmethod
    def override(position_id, amount, as_of=START, currency="USD"):
        return PositionValuationOverride(position_id, Valuation(currency, D(amount), as_of))

    def test_scenario_and_local_precedence_preserve_authoritative_positions(self):
        saved = [
            self.override("cash", "8000"), self.override("car", "7000"),
            self.override("loan", "3000"), self.override("joint", "9000"),
        ]
        scenario = Scenario(
            Revision("position-case", "1"), "Opening position case", self.profile.revision.id,
            overrides=AnalysisOverrides(position_valuations=saved),
        )
        local = AnalysisOverrides(position_valuations=[self.override("cash", "0")])
        baseline = resolve_analysis(self.request, **self.context)
        hypothetical = resolve_analysis(self.request, scenario=scenario, **self.context)
        resolved = resolve_analysis(self.request, scenario=scenario, local=local, **self.context)
        self.assertIs(resolved.profile, self.profile)
        self.assertEqual(baseline.opening_valuations()["cash"].amount, D("5000"))
        self.assertEqual(hypothetical.opening_valuations()["cash"].amount, D("8000"))
        self.assertEqual(resolved.opening_valuations()["cash"].amount, D(0))
        self.assertEqual(resolved.opening_valuations()["car"].amount, D("7000"))
        self.assertEqual(resolved.opening_valuations()["loan"].amount, D("3000"))
        self.assertEqual(resolved.opening_valuations()["joint"].amount, D("9000"))
        self.assertEqual(resolved.opening_valuations()["ira"].amount, D("12000"))
        saved_cash = next(entry for entry in scenario.overrides.position_valuations
                          if entry.position_id == "cash")
        self.assertEqual(saved_cash, saved[0])
        self.assertEqual(resolve_analysis(self.request, **self.context), baseline)
        origins = {item.field: item.source for item in resolved.origins}
        self.assertEqual(origins["opening.positions.cash.valuation"], Source(SourceKind.LOCAL_OVERRIDE))
        for position_id in ("car", "joint", "loan"):
            self.assertEqual(origins[f"opening.positions.{position_id}.valuation"],
                             Source(SourceKind.SCENARIO_OVERRIDE, scenario.revision))
        self.assertEqual(ResolvedAnalysis.from_json(resolved.to_json()), resolved)

    def test_invalid_and_shadowed_overrides_are_rejected(self):
        for override, message in (
            (self.override("missing", "5"), "unknown or out-of-scope position"),
            (self.override("blair-cash", "5"), "unknown or out-of-scope position"),
            (self.override("cash", "5", currency="EUR"), "requires USD"),
            (self.override("cash", "5", as_of=date(2030, 1, 2)), "dated after"),
        ):
            local = AnalysisOverrides(position_valuations=[override])
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, message):
                resolve_analysis(self.request, local=local, **self.context)
        scenario = Scenario(
            Revision("shadowed", "1"), "Shadowed", self.profile.revision.id,
            overrides=AnalysisOverrides(position_valuations=[self.override("cash", "7", currency="EUR")]),
        )
        with self.assertRaisesRegex(ValueError, "requires USD"):
            resolve_analysis(self.request, scenario=scenario, **self.context,
                             local=AnalysisOverrides(position_valuations=[self.override("cash", "0")]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            AnalysisOverrides(position_valuations=[self.override("cash", "7"), self.override("cash", "8")])
        for amount, as_of in (("1", None), ("-1", START), ("0.000000001", START), ("NaN", START)):
            with self.subTest(amount=amount, as_of=as_of), self.assertRaises(ValueError):
                self.override("cash", amount, as_of)
        with self.assertRaisesRegex(ValueError, "explicit dated amount"):
            PositionValuationOverride("cash", Valuation("USD"))

    def test_holdings_consistency_applies_to_each_override(self):
        cash = next(item for item in self.profile.accounts if item.id == "cash")
        holdings = [Holding("disclosed-cash", AssetClass.CASH, value=usd("4000"))]
        cash = replace(cash, holdings=holdings)
        profile = replace(self.profile, accounts=[
            cash if item.id == "cash" else item for item in self.profile.accounts
        ])
        context = {**self.context, "profile": profile}
        for override, message in (
            (self.override("cash", "3999"), "holding values exceed"),
            (self.override("cash", "6000", date(2029, 12, 31)), "original valuation date"),
        ):
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, message):
                resolve_analysis(self.request, **context,
                                 local=AnalysisOverrides(position_valuations=[override]))
        resolved = resolve_analysis(
            self.request, **context,
            local=AnalysisOverrides(position_valuations=[
                self.override("cash", "6000"), self.override("ira", "0", date(2029, 12, 31)),
            ]),
        )
        self.assertEqual(resolved.opening_valuations()["cash"].amount, D("6000"))
        self.assertEqual(resolved.opening_valuations()["ira"].amount, D(0))
        self.assertEqual(next(item for item in resolved.profile.accounts if item.id == "cash"), cash)

    def test_hypothetical_opening_value_can_fill_an_unknown_baseline(self):
        profile = replace(self.profile, accounts=[
            replace(account, valuation=Valuation("USD")) if account.id == "cash" else account
            for account in self.profile.accounts
        ])
        context = {**self.context, "profile": profile}
        with self.assertRaisesRegex(MissingAnalysisInput, "opening amount for cash"):
            resolve_analysis(self.request, **context)
        resolved = resolve_analysis(self.request, **context,
                                    local=AnalysisOverrides(position_valuations=[self.override("cash", "0")]))
        self.assertEqual(resolved.opening_valuations()["cash"].amount, D(0))
        self.assertIsNone(next(item for item in resolved.profile.accounts if item.id == "cash").valuation.amount)

    def test_presets_and_defaults_cannot_supply_position_overrides(self):
        for config in (illustrative_preset(), research_defaults()):
            with self.subTest(config=type(config)), self.assertRaises(TypeError):
                replace(config, position_valuations=[self.override("cash", "0")])

    def test_snapshot_round_trip_immutability_and_content_identification(self):
        changes = [self.override("cash", "0"), self.override("car", "7000")]
        snapshot = resolve_analysis(self.request, **self.context,
                                    local=AnalysisOverrides(position_valuations=changes))
        canonical = snapshot.to_json()
        original_id = snapshot.content_id
        changes.reverse()
        equivalent = resolve_analysis(self.request, **self.context,
                                      local=AnalysisOverrides(position_valuations=changes))
        self.assertEqual(equivalent.content_id, original_id)
        changes.clear()
        valuations = snapshot.opening_valuations()
        valuations.clear()
        with self.assertRaises(FrozenInstanceError):
            snapshot.position_valuations[0].valuation.amount = D(10)
        self.assertEqual(snapshot.to_json(), canonical)
        restored = ResolvedAnalysis.from_json(canonical)
        self.assertEqual(restored.content_id, original_id)
        self.assertEqual(restored, snapshot)
        self.assertEqual(restored.opening_valuations(), snapshot.opening_valuations())
        self.assertNotEqual(resolve_analysis(self.request, **self.context).content_id, original_id)
        payload = json.loads(canonical)
        origin = next(item for item in payload["origins"] if item["field"] == "opening.positions.cash.valuation")
        origin["source"]["kind"] = SourceKind.PRESET.value
        with self.assertRaisesRegex(ValueError, "require local or matching scenario provenance"):
            ResolvedAnalysis.from_json(json.dumps(payload))


class SnapshotTests(unittest.TestCase):
    def test_unrelated_profile_update_changes_context_id_without_changing_opening_values(self):
        profile, plan = household_example()
        request = projection_request()
        context = dict(plan=plan, preset=illustrative_preset())
        original = resolve_analysis(request, profile=profile, **context)
        changed = replace(profile, accounts=[
            replace(account, valuation=Valuation("USD", D("4000"), START))
            if account.id == "blair-cash" else account for account in profile.accounts
        ])
        revised = resolve_analysis(request, profile=changed, **context)
        self.assertEqual(revised.opening_valuations(), original.opening_valuations())
        self.assertNotEqual(revised.content_id, original.content_id)

    def test_source_mutation_revisions_and_snapshot_immutability(self):
        profile, plan = individual_example()
        preset = illustrative_preset()
        accounts = list(profile.accounts)
        activity_amounts = [ActivityAmountOverride("save", usd("400"))]
        overrides = AnalysisOverrides(activity_amounts=activity_amounts)
        profile = replace(profile, accounts=accounts)
        request = projection_request()
        original = resolve_analysis(request, profile=profile, plan=plan, preset=preset, local=overrides)
        initial_json = original.to_json()
        initial_identifier = original.content_id
        accounts[0] = replace(accounts[0], valuation=Valuation("USD", D("6000"), START))
        activity_amounts.clear()
        with self.assertRaises(FrozenInstanceError):
            original.profile.accounts[0].valuation.amount = D(0)
        with self.assertRaises(FrozenInstanceError):
            original.plan.activities = ()
        self.assertEqual(original.to_json(), initial_json)
        self.assertEqual(original.content_id, initial_identifier)
        self.assertEqual(amount_for(original.plan, "save"), usd("400"))

        newer_profile = replace(profile, revision=Revision("profile", "2"), accounts=accounts)
        newer_preset = replace(preset, revision=Revision(preset.revision.id, "3"),
                               assumptions=EconomicAssumptions(annual_investment_return=D("0.07")))
        newer = resolve_analysis(request, profile=newer_profile, plan=plan, preset=newer_preset)
        self.assertEqual(newer.profile.accounts[0].valuation.amount, D("6000"))
        self.assertEqual(newer.assumptions.annual_investment_return, D("0.07"))
        self.assertEqual(newer.preset_revision.version, "3")
        self.assertEqual(original.profile.accounts[0].valuation.amount, D("5000"))
        self.assertEqual(original.assumptions.annual_investment_return, D("0.05"))
        self.assertNotEqual(newer.content_id, initial_identifier)

    def test_snapshot_round_trip_and_canonical_id(self):
        profile, plan = household_example()
        request = projection_request(
            HOUSEHOLD, methodology=Revision("test-methodology", "candidate"),
            external_data=[Revision("test-feed-b", "1"), Revision("test-feed-a", "2")],
            stochastic=StochasticExecution(seed=0, path_count=16),
        )
        original = resolve_analysis(request, profile=profile, plan=plan, defaults=research_defaults())
        canonical = original.to_json()
        data = json.loads(canonical)
        self.assertEqual(data["profile"]["accounts"][0]["valuation"]["amount"], "2000")
        loaded = ResolvedAnalysis.from_json(json.dumps(data, indent=2))
        self.assertEqual(loaded, original)
        self.assertEqual(loaded.to_json(), canonical)
        self.assertEqual(loaded.content_id, original.content_id)

        reordered = [replace(
            item, valuation=replace(item.valuation, amount=D(str(item.valuation.amount) + ".00")),
        ) for item in reversed(profile.accounts)]
        equivalent = resolve_analysis(
            replace(request, external_data=list(reversed(request.external_data))),
            profile=replace(profile, accounts=reordered), plan=replace(plan, activities=reversed(plan.activities)),
            defaults=research_defaults(),
        )
        self.assertEqual(equivalent.content_id, original.content_id)
        changed = resolve_analysis(replace(request, stochastic=StochasticExecution(1, 16)),
                                   profile=profile, plan=plan, defaults=research_defaults())
        self.assertNotEqual(changed.content_id, original.content_id)

    def test_snapshot_decoder_rejects_unsupported_or_invalid_payload(self):
        snapshot = resolve_analysis(AnalysisRequest(
            AnalysisType.LOAN_PAYMENT, LoanPaymentInputs(usd(1200), D(0), 12),
        ))
        payload = json.loads(snapshot.to_json())
        for changes in (
            {"schema_version": 1}, {"schema_version": 3}, {"schema_version": True},
            {"extra": "unknown"}, {"origins": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ResolvedAnalysis.from_json(json.dumps({**payload, **changes}))
        with self.assertRaisesRegex(ValueError, "duplicate snapshot key"):
            ResolvedAnalysis.from_json('{"schema_version":1,"schema_version":2}')
        payload["request"]["inputs"]["annual_rate"] = 0.05
        with self.assertRaises(ValueError):
            ResolvedAnalysis.from_json(json.dumps(payload))

    def test_resolver_runs_with_only_standard_library(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent("""
            import sys
            from decimal import Decimal

            sys.path.insert(0, sys.argv[1])
            from moneylab.configuration.models import AnalysisRequest, AnalysisType, LoanPaymentInputs
            from moneylab.configuration.resolve import resolve_analysis
            from moneylab.configuration.snapshot import ResolvedAnalysis
            from moneylab.domain.values import Money

            request = AnalysisRequest(
                AnalysisType.LOAN_PAYMENT, LoanPaymentInputs(Money(Decimal(100), "USD"), Decimal(0), 12),
            )
            snapshot = resolve_analysis(request)
            assert ResolvedAnalysis.from_json(snapshot.to_json()) == snapshot
        """)
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", script, str(root)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
