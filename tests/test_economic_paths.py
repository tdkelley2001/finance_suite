"""Independent cases for realized paths and the shared monthly executor."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from moneylab._calendar import month_boundary
from moneylab.configuration.models import (
    AnalysisOverrides, AnalysisRequest, AnalysisType, LoanPaymentInputs,
    PositionValuationOverride, Scenario, StochasticExecution,
)
from moneylab.configuration.resolve import resolve_analysis
from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.planning import ActivityKind
from moneylab.domain.profile import Asset, AssetKind, Owner, Ownership
from moneylab.domain.values import Revision
from moneylab.economics import (
    AnnualRate, EconomicMonth, EconomicObservation, EconomicPath, EconomicPathError,
    EconomicSeries, PathMetadata, SeriesKind, constant_path,
)
from moneylab.projection import (
    METHODOLOGY, PATH_METHODOLOGY, PositionExposure, ProjectionRangeError,
    ProjectionReadinessError, project_economic_path, project_monthly,
)
from moneylab.projection.results import EffectKind, ProjectionStatus
from moneylab.projection.accounting import ReconciliationError

from test_monthly_projection import (
    APR, FEB, JAN, MAR, SOLE, account, activity, amounts, debt, payment, profile, snapshot, usd, value,
)


METADATA = PathMetadata(Revision("explicit-fixture", "1"), source=Revision("synthetic-values", "1"))
MARKET = EconomicSeries("market", SeriesKind.INVESTMENT_RETURN)
PROPERTY = EconomicSeries("property", SeriesKind.INVESTMENT_RETURN)
PRICES = EconomicSeries("prices", SeriesKind.INFLATION)


def explicit_path(*columns, start_on=JAN, metadata=METADATA):
    series, values = zip(*columns)
    rows = zip(*values, strict=True)
    return EconomicPath(series, [
        EconomicMonth(
            month_boundary(start_on, offset), month_boundary(start_on, offset + 1),
            [EconomicObservation(item.id, D(rate)) for item, rate in zip(series, row)],
        )
        for offset, row in enumerate(rows)
    ], metadata)


def exposed(key, series=MARKET):
    return PositionExposure(key, series_id=series.id)


def static(key):
    return PositionExposure(key, annual_effective_rate=D(0))


class EconomicPathContractTests(unittest.TestCase):
    def test_canonical_round_trip_captures_nested_inputs_and_distinguishes_provenance(self):
        observations = [EconomicObservation("prices", D(".02")), EconomicObservation("market", D(".10"))]
        months = [EconomicMonth(JAN, FEB, observations)]
        series = [PRICES, MARKET]
        assumptions = [AnnualRate("prices", D(".024"))]
        metadata = replace(METADATA, annual_assumptions=assumptions, seed=0, path_index=2,
                           random_algorithm=Revision("example-provenance", "1"))
        path = EconomicPath(series, months, metadata)
        expected = path.to_json()
        content_id = path.content_id
        observations.clear()
        months.clear()
        series.clear()
        assumptions.clear()
        self.assertEqual(path.to_json(), expected)
        self.assertEqual(path.content_id, content_id)
        self.assertEqual(EconomicPath.from_json(expected), path)
        self.assertEqual(EconomicPath.from_json(expected).content_id, content_id)
        self.assertEqual(json.loads(expected)["months"][0]["observations"][0]["monthly_rate"], "0.1")
        ordered = explicit_path((MARKET, ["0.1000"]), (PRICES, ["0.0200"]), metadata=metadata)
        self.assertEqual(ordered.to_json(), expected)
        self.assertNotEqual(replace(path, metadata=replace(metadata, seed=1)).content_id, content_id)
        with self.assertRaises(FrozenInstanceError):
            path.months[0].observations[0].monthly_rate = D(0)
        with self.assertRaises(EconomicPathError):
            EconomicPath.from_json(expected.replace('"schema_version":1', '"schema_version":2'))

    def test_subpath_preserves_overlap_and_parent_identity(self):
        path = explicit_path((MARKET, [".1", "-.2", ".05"]), (PRICES, ["0", ".01", ".02"]))
        selected = path.subpath(FEB, APR)
        self.assertEqual(selected.months, path.months[1:])
        self.assertEqual((selected.start_on, selected.end_before, selected.horizon_months), (FEB, APR, 2))
        self.assertEqual(selected.metadata.parent_content_id, path.content_id)
        self.assertNotEqual(selected.content_id, path.content_id)
        self.assertIs(path.subpath(JAN, APR), path)
        self.assertEqual(selected.content_id, path.subpath(FEB, APR).content_id)
        for start, end in ((FEB, FEB), (JAN, date(2030, 4, 2)), (date(2029, 12, 1), MAR)):
            with self.subTest(start=start, end=end), self.assertRaises(EconomicPathError):
                path.subpath(start, end)

    def test_invalid_periods_and_incomplete_series_fail_on_construction(self):
        path = explicit_path((MARKET, ["0", ".01", ".02"]))
        for invalid in ((path.months[0], path.months[0]), path.months[::2], tuple(reversed(path.months))):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(EconomicPathError, "chronological, unique"):
                replace(path, months=invalid)
        for start, end in ((date(2030, 1, 2), FEB), (JAN, MAR), (JAN, JAN)):
            with self.subTest(start=start, end=end), self.assertRaises(EconomicPathError):
                EconomicMonth(start, end, [])
        with self.assertRaisesRegex(EconomicPathError, "declared series exactly"):
            EconomicPath([MARKET, PRICES], path.months, METADATA)
        with self.assertRaisesRegex(EconomicPathError, "declared series exactly"):
            EconomicPath([PRICES], path.months, METADATA)
        with self.assertRaisesRegex(EconomicPathError, "duplicate"):
            EconomicMonth(JAN, FEB, [EconomicObservation("market", D(0))] * 2)
        with self.assertRaisesRegex(EconomicPathError, "duplicate"):
            replace(path, series=[MARKET, MARKET])
        with self.assertRaisesRegex(EconomicPathError, "at most one inflation"):
            explicit_path((PRICES, ["0"]), (EconomicSeries("other", SeriesKind.INFLATION), ["0"]))
        with self.assertRaisesRegex(EconomicPathError, "known series"):
            replace(path, metadata=replace(METADATA, annual_assumptions=[AnnualRate("other", D(0))]))

    def test_rate_semantics_and_constant_generation_metadata(self):
        for rate in (D("NaN"), D("Infinity"), D("-1.00000001"), D("1e18"), D("1e-61"), 0.01):
            with self.subTest(rate=rate), self.assertRaises(EconomicPathError):
                EconomicObservation("market", rate)
        with self.assertRaisesRegex(EconomicPathError, "inflation must be greater than -1"):
            explicit_path((PRICES, ["-1"]))
        full_loss = explicit_path((MARKET, ["-1"]))
        self.assertEqual(full_loss.months[0].observations[0].monthly_rate, -1)
        assumptions = [AnnualRate("prices", D(".03")), AnnualRate("market", D(".12"))]
        path = constant_path(JAN, 2, [PRICES, MARKET], assumptions, source=METADATA.source)
        self.assertEqual(path.metadata.annual_assumptions, tuple(reversed(assumptions)))
        self.assertEqual(path.metadata.source, METADATA.source)
        monthly = path.months[0].observations[0].monthly_rate
        self.assertAlmostEqual((1 + monthly) ** 12, D("1.12"), delta=D("1e-25"))
        self.assertEqual(path.months[0].observations, path.months[1].observations)
        with self.assertRaisesRegex(EconomicPathError, "assumptions must cover"):
            constant_path(JAN, 1, [PRICES, MARKET], assumptions[:1])


class PathExecutionTests(unittest.TestCase):
    def test_constant_path_equivalence_including_debt_inflation_and_settlement(self):
        records = profile(account("cash", 15000), account("invest", 1000), liabilities=[debt(12000, ".06")])
        save = activity("save", ActivityKind.CONTRIBUTION, 100, source="cash", destination="invest")
        plan = [payment("1032.80"), save]
        deterministic = project_monthly(snapshot(
            records, months=12, rates={"cash": "0", "invest": ".12"}, inflation=".03", real=True,
            activities=plan,
        ))
        path = constant_path(JAN, 12, [MARKET, PRICES], [AnnualRate("market", D(".12")), AnnualRate("prices", D(".03"))])
        inputs = snapshot(records, months=12, rates={}, real=True, activities=plan, methodology=PATH_METHODOLOGY)
        inputs = ResolvedAnalysis.from_json(inputs.to_json())
        path_result = project_economic_path(inputs, path, [static("cash"), exposed("invest")])
        result = path_result.projection
        self.assertEqual(replace(result, input_content_id=deterministic.input_content_id,
                                 methodology=deterministic.methodology,
                                 annual_inflation=deterministic.annual_inflation,
                                 position_growth=deterministic.position_growth).to_json(), deterministic.to_json())
        self.assertEqual(result.methodology, PATH_METHODOLOGY)
        self.assertIsNone(result.annual_inflation)
        self.assertEqual(path_result.execution.path_methodology, path.metadata.methodology)
        self.assertEqual(path_result.execution.execution_methodology, PATH_METHODOLOGY)
        self.assertEqual(path_result.execution.financial_methodology, METHODOLOGY)
        self.assertTrue(any(effect.kind is EffectKind.PRINCIPAL_PAID for effect in result.months[0].effects))
        self.assertEqual(result.months[0].reconciliation.net_worth_residual, 0)

    def test_realized_series_apply_once_with_independent_positions_and_variable_inflation(self):
        home = Asset("home", "Home", AssetKind.REAL_ESTATE, SOLE, value(300))
        records = profile(account("a", 1000), account("b", 200), assets=[home])
        income = activity("pay", ActivityKind.EXTERNAL_INCOME, 50, destination="b")
        path = explicit_path(
            (MARKET, [".10", "-.20", ".05"]), (PROPERTY, ["0", ".10", "-.10"]),
            (PRICES, [".02", "-.01", ".03"]),
        )
        exposures = [exposed("a"), exposed("b"), exposed("home", PROPERTY)]
        nominal = project_economic_path(
            snapshot(records, months=3, rates={}, activities=[income]), path, exposures,
        ).projection
        real = project_economic_path(
            snapshot(records, months=3, rates={}, real=True, activities=[income]), path, exposures,
        ).projection
        self.assertEqual([amounts(item.closing) for item in real.months], [
            {"a": 1100, "b": 270, "home": 300},
            {"a": 880, "b": 266, "home": 330},
            {"a": 924, "b": D("329.30"), "home": 297},
        ])
        self.assertEqual(real.opening.inflation_index, 1)
        self.assertEqual(real.months[-1].closing.inflation_index, D("1.040094"))
        self.assertEqual(real.months[-1].closing.net_worth, D("1550.30"))
        expected_real = (D("1550.30") / D("1.040094")).quantize(D(".00000001"))
        self.assertEqual(real.months[-1].closing.real_net_worth, expected_real)
        self.assertEqual([item.effects for item in real.months], [item.effects for item in nominal.months])
        self.assertEqual([item.reconciliation for item in real.months], [item.reconciliation for item in nominal.months])
        self.assertTrue(all(item.closing.real_net_worth is None for item in nominal.months))

    def test_sequence_of_returns_with_and_without_month_end_contributions(self):
        records = profile(account("invest", 1000))
        paths = [explicit_path((MARKET, rates)) for rates in ([".10", "-.20"], ["-.20", ".10"])]
        exposure = [exposed("invest")]
        base = snapshot(records, months=2, rates={})
        no_flows = [project_economic_path(base, path, exposure).projection for path in paths]
        self.assertEqual([result.months[-1].closing.net_worth for result in no_flows], [880, 880])
        deposit = activity("deposit", ActivityKind.EXTERNAL_INCOME, 100, destination="invest")
        with_flows = snapshot(records, months=2, rates={}, activities=[deposit])
        results = [project_economic_path(with_flows, path, exposure).projection for path in paths]
        self.assertEqual([result.months[-1].closing.net_worth for result in results], [1060, 1090])

    def test_common_path_across_scenarios_and_explicit_calendar_slices(self):
        path = explicit_path((MARKET, [".10", "-.20", ".05"]), (PRICES, [".02", ".01", "0"]))
        before = path.to_json()
        records = profile(account("invest", 100))
        override = PositionValuationOverride("invest", value(200))
        scenario = Scenario(Revision("alternate", "1"), "Higher opening", "profile",
                            overrides=AnalysisOverrides(position_valuations=[override]))
        baseline = snapshot(records, months=3, rates={})
        alternative = snapshot(records, months=3, rates={}, scenario=scenario)
        baseline_run = project_economic_path(baseline, path, [exposed("invest")])
        alternative_run = project_economic_path(alternative, path, [exposed("invest")])
        self.assertEqual(baseline_run.execution.path_content_id, alternative_run.execution.path_content_id)
        self.assertEqual([result.closing.net_worth for result in baseline_run.projection.months],
                         [110, 88, D("92.4")])
        self.assertEqual([result.closing.net_worth for result in alternative_run.projection.months],
                         [220, 176, D("184.8")])
        static_run = project_economic_path(alternative, path, [static("invest")])
        self.assertEqual(static_run.execution.path_content_id, alternative_run.execution.path_content_id)
        self.assertEqual([item.closing.net_worth for item in static_run.projection.months], [200, 200, 200])
        self.assertNotEqual(baseline_run.execution_content_id, alternative_run.execution_content_id)
        self.assertEqual(path.to_json(), before)
        self.assertEqual(baseline.opening_valuations()["invest"].amount, 100)

        aligned = snapshot(profile(account("invest", 100, as_of=FEB)), start=FEB, months=2, rates={})
        overlap = project_economic_path(aligned, path.subpath(FEB, APR), [exposed("invest")])
        self.assertEqual([item.closing.net_worth for item in overlap.projection.months], [80, 84])
        self.assertEqual(overlap.projection.opening.inflation_index, 1)
        self.assertEqual(overlap.projection.months[-1].closing.inflation_index, D("1.01"))

    def test_execution_identity_captures_path_exposure_snapshot_and_metadata(self):
        path = explicit_path((MARKET, [".10"]), (PROPERTY, [".10"]))
        records = profile(account("a", 100), account("b", 50))
        inputs = snapshot(records, rates={})
        exposures = [exposed("a"), static("b")]
        result = project_economic_path(inputs, path, exposures)
        serialized = result.to_json()
        exposures.reverse()
        with localcontext(prec=5):
            replay = project_economic_path(inputs, EconomicPath.from_json(path.to_json()), exposures)
        self.assertEqual(replay.to_json(), serialized)
        self.assertEqual(replay.execution_content_id, result.execution_content_id)
        exposures.clear()
        self.assertEqual(result.to_json(), serialized)
        with self.assertRaises(FrozenInstanceError):
            result.execution.exposures[0].series_id = "other"
        json_ref = json.loads(serialized)["execution"]
        self.assertEqual(json_ref["path_content_id"], path.content_id)
        self.assertEqual(json_ref["input_content_id"], inputs.content_id)
        self.assertEqual(json_ref["path_schema_version"], path.schema_version)
        variants = [
            (inputs, path, [exposed("a", PROPERTY), static("b")]),
            (inputs, explicit_path((MARKET, [".20"]), (PROPERTY, [".10"])), [exposed("a"), static("b")]),
            (inputs, replace(path, metadata=replace(METADATA, source=Revision("synthetic-values", "2"))),
             [exposed("a"), static("b")]),
            (snapshot(replace(records, revision=Revision("profile", "2")), rates={}), path,
             [exposed("a"), static("b")]),
        ]
        for new_inputs, new_path, new_exposures in variants:
            with self.subTest(inputs=new_inputs.content_id, path=new_path.content_id, exposures=new_exposures):
                revised = project_economic_path(new_inputs, new_path, new_exposures)
                self.assertNotEqual(revised.execution_content_id, result.execution_content_id)

    def test_contextual_general_return_and_conflicting_growth(self):
        from moneylab.configuration.models import EconomicAssumptions, Preset

        records = profile(account("invest", 100))
        path = explicit_path((MARKET, [".1"]))
        preset = Preset(Revision("test-market", "1"), "Test market",
                        assumptions=EconomicAssumptions(annual_investment_return=D(".9")))
        inputs = snapshot(records, rates={}, preset=preset)
        result = project_economic_path(inputs, path, [exposed("invest")])
        self.assertEqual(result.projection.months[-1].closing.net_worth, 110)
        self.assertNotIn("annual_investment_return", result.to_json())
        legacy = snapshot(records, rates={"invest": ".12"})
        for conflict in (exposed("invest"), static("invest")):
            with self.subTest(conflict=conflict), self.assertRaisesRegex(EconomicPathError, "conflicts"):
                project_economic_path(legacy, path, [conflict])
        matched = project_economic_path(legacy, path, [PositionExposure("invest", annual_effective_rate=D(".12"))])
        self.assertEqual(matched.projection.months, project_monthly(legacy).months)

    def test_invalid_mappings_alignment_and_inflation(self):
        records = profile(account("a", 100), account("outside", 200, ownership=Ownership([Owner("blair")])),
                          liabilities=[debt(0, 0)])
        path = explicit_path((MARKET, [".1"]), (PRICES, [".01"]))
        valid_inputs = snapshot(records, rates={})
        for invalid, message in (
            ([], "missing growth exposures"),
            ([exposed("a"), static("a")], "duplicate"),
            ([exposed("unknown")], "in-scope account or asset"),
            ([exposed("outside")], "in-scope account or asset"),
            ([exposed("loan")], "in-scope account or asset"),
            ([PositionExposure("a", series_id="unknown")], "known investment"),
            ([exposed("a", PRICES)], "known investment"),
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(EconomicPathError, message):
                project_economic_path(valid_inputs, path, invalid)
        with self.assertRaisesRegex(EconomicPathError, "exactly"):
            project_economic_path(snapshot(records, months=2, rates={}), path, [exposed("a")])
        with self.assertRaisesRegex(EconomicPathError, "exactly"):
            two_months = explicit_path((MARKET, [".1", "0"]))
            project_economic_path(valid_inputs, two_months, [exposed("a")])
        with self.assertRaisesRegex(EconomicPathError, "exactly"):
            later = explicit_path((MARKET, [".1"]), start_on=FEB)
            project_economic_path(valid_inputs, later, [exposed("a")])
        without_inflation = explicit_path((MARKET, [".1"]))
        with self.assertRaisesRegex(EconomicPathError, "complete monthly inflation"):
            project_economic_path(snapshot(records, real=True, rates={}), without_inflation, [exposed("a")])
        for candidate in (path, without_inflation):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(EconomicPathError, "annual inflation to be unset"):
                project_economic_path(snapshot(records, inflation=".03", rates={}), candidate, [exposed("a")])
        with self.assertRaisesRegex(EconomicPathError, "exactly one"):
            PositionExposure("a", series_id="market", annual_effective_rate=D(0))

    def test_unsupported_analysis_or_methodology_retains_financial_readiness_errors(self):
        financial = profile(account("a", 100))
        path = explicit_path((MARKET, [".01"]))
        loan = resolve_analysis(AnalysisRequest(AnalysisType.LOAN_PAYMENT, LoanPaymentInputs(usd(100), D(0), 12)))
        for inputs, code in (
            (loan, "analysis_type"),
            (snapshot(financial, rates={}, methodology=METHODOLOGY), "methodology"),
            (snapshot(financial, rates={}, stochastic=StochasticExecution(0, 1)), "stochastic"),
            (snapshot(profile(account("a", 100, as_of=date(2029, 12, 1))), rates={}), "unaligned_valuation"),
        ):
            with self.subTest(code=code), self.assertRaises(ProjectionReadinessError) as raised:
                project_economic_path(inputs, path, [exposed("a")])
            self.assertIn(code, [issue.code for issue in raised.exception.issues])

    def test_funding_stops_are_atomic_and_distinct_from_financial_range_failures(self):
        records = profile(account("cash", 100), account("reserve", 1000))
        bill = activity("bill", ActivityKind.EXTERNAL_EXPENSE, 60, source="cash")
        inputs = snapshot(records, rates={}, activities=[bill])
        path = explicit_path((MARKET, ["-.5"]))
        stopped = project_economic_path(inputs, path, [exposed("cash"), static("reserve")]).projection
        self.assertEqual(stopped.status, ProjectionStatus.STOPPED)
        self.assertEqual(stopped.completed_months, 0)
        self.assertEqual(amounts(stopped.opening), {"cash": 100, "reserve": 1000})
        shortfall = stopped.termination.shortfalls[0]
        self.assertEqual((shortfall.available, shortfall.required, shortfall.unfunded), (50, 60, 10))

        full_loss = explicit_path((MARKET, ["-1", ".5"]))
        recover = project_economic_path(
            snapshot(profile(account("cash", 100)), months=2, rates={},
                     activities=[activity("credit", ActivityKind.EXTERNAL_INCOME, 20, destination="cash", end=FEB)]),
            full_loss, [exposed("cash")],
        ).projection
        self.assertEqual([item.closing.net_worth for item in recover.months], [20, 30])
        enormous = explicit_path((MARKET, ["9e17"]))
        with self.assertRaisesRegex(ProjectionRangeError, "growth for cash"):
            project_economic_path(snapshot(profile(account("cash", "9e17")), rates={}), enormous, [exposed("cash")])

    def test_nominal_stop_matches_m03_and_stdlib_execution_is_isolated(self):
        bill = activity("bill", ActivityKind.EXTERNAL_EXPENSE, 60, source="cash")
        records = profile(account("cash", 100))
        initial = project_monthly(snapshot(records, months=2, activities=[bill]))
        path = explicit_path((MARKET, ["0", "0"]))
        stopped = project_economic_path(snapshot(records, months=2, rates={}, activities=[bill]), path, [exposed("cash")])
        self.assertEqual(stopped.projection.termination, initial.termination)
        self.assertEqual(stopped.projection.months, initial.months)
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent("""
            import sys
            sys.path[:0] = sys.argv[1:]
            from test_economic_paths import MARKET, account, explicit_path, exposed, profile, project_economic_path, snapshot
            result = project_economic_path(
                snapshot(profile(account("a", 100)), rates={}),
                explicit_path((MARKET, [".1"])), [exposed("a")],
            )
            assert result.projection.months[0].closing.net_worth == 110
        """)
        run = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(root), str(root / "tests")],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_debt_and_reconciliation_error_semantics_through_the_path_driver(self):
        path = explicit_path((MARKET, [".01"]))
        debt_inputs = snapshot(profile(account("cash", 100), liabilities=[debt(100, ".12")]), rates={})
        stopped = project_economic_path(debt_inputs, path, [static("cash")]).projection
        self.assertEqual(stopped.status, ProjectionStatus.STOPPED)
        self.assertEqual(stopped.completed_months, 0)
        self.assertEqual(stopped.termination.issues[0].code, "missing_debt_payment")
        self.assertFalse(stopped.termination.shortfalls)
        inputs = snapshot(profile(account("cash", 100)), rates={})
        with patch("moneylab.projection.engine.reconcile", side_effect=ReconciliationError("injected mismatch")):
            with self.assertRaisesRegex(ReconciliationError, "injected mismatch"):
                project_economic_path(inputs, path, [static("cash")])
