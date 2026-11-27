"""Characterization tests for behavior preserved during the M01 extraction."""

import json
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import unittest
from unittest.mock import patch

import pandas as pd

from moneylab.engine import models
from rent_vs_buy.samplers.deterministic import deterministic_run
from rent_vs_buy.samplers.monte_carlo import monte_carlo_run
from suite import calculations, state as state_adapter

TEST_DIR = Path(__file__).resolve().parent


class EngineBoundaryTests(unittest.TestCase):
    def test_engine_import_does_not_load_streamlit_or_supabase(self):
        script = dedent("""
            import math
            import sys

            sys.path.insert(0, sys.argv[1])
            from moneylab.engine import FinancialAccount, fixed_payment
            from budget.engine import calculate_budget_summary
            from budget.models import BudgetAssumptions, BudgetProfile
            from emergency_fund.engine import EmergencyFundInputs, calculate_emergency_fund
            from housing_affordability.engine import monthly_mortgage_payment
            from net_worth.engine import calculate_balance_sheet
            from rent_vs_buy.samplers.deterministic import deterministic_run
            from rent_vs_buy.samplers.monte_carlo import monte_carlo_run

            assert fixed_payment(1_200, 0, 1) == 100
            assert calculate_balance_sheet(
                [FinancialAccount("Cash", "Checking", 500)], [], [],
            ).net_worth == 500
            profile = BudgetProfile(assumptions=BudgetAssumptions(net_monthly_income=500))
            assert calculate_budget_summary(profile).buffer == 500
            inputs = EmergencyFundInputs(100, 150, 500, 500, 500, 6)
            assert calculate_emergency_fund(inputs).target_emergency_fund == 600
            assert monthly_mortgage_payment(1_200, 0, 1) == 100
            result = deterministic_run("Baseline", "US", horizon=1)
            assert len(result.yearly) == 1
            assert math.isfinite(result.summary["net_worth_diff"])
            simulations, _ = monte_carlo_run(
                scenario="Baseline", region="US", overrides=None, horizon=1,
                rent_basis="market", married=False, sell_at_end=True, n_sims=2,
                seed=1729, mc_profile="default", param_sd_scale=1.0, path_sd_scale=1.0,
            )
            assert len(simulations) == 2
            assert all(math.isfinite(value) for value in simulations["net_worth_diff"])

            forbidden = sorted(
                name for name in sys.modules
                if name.partition(".")[0] in {"streamlit", "supabase"}
            )
            assert not forbidden, f"Engine loaded forbidden modules: {forbidden}"
        """)
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script, str(TEST_DIR.parent)],
            cwd=TEST_DIR.parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_suite_state_types_are_compatibility_reexports(self):
        for name in (
            "Asset", "AssumptionsState", "BalanceSheetState", "DataProvenance",
            "FinancialAccount", "FinancialGoal", "Liability", "MonthlyCashFlowState",
            "ProfileState", "Scenario", "ScenariosState", "SharedCashFlowState",
            "ToolOutputsState", "UserState",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(state_adapter, name), getattr(models, name))

    def test_suite_calculations_are_compatibility_reexports(self):
        from moneylab.engine import calculations as engine_calculations

        for name in calculations.__all__:
            with self.subTest(name=name):
                self.assertIs(getattr(calculations, name), getattr(engine_calculations, name))


class PersistedStateCompatibilityTests(unittest.TestCase):
    def test_legacy_json_round_trip_preserves_supported_fields(self):
        path = TEST_DIR / "fixtures" / "pre_m01_synthetic_profile.json"
        legacy = json.loads(path.read_text(encoding="utf-8"))
        decoded = state_adapter.state_from_dict(legacy)
        self.assertEqual(decoded.updated_at, legacy["updated_at"])
        self.assertIsInstance(decoded.profile.accounts[0], models.FinancialAccount)
        self.assertIsInstance(decoded.profile.goals[0], models.FinancialGoal)
        self.assertIsInstance(decoded.assumptions.provenance["inflation"], models.DataProvenance)
        self.assertIsInstance(decoded.scenarios.items["Higher inflation"], models.Scenario)

        expected = deepcopy(legacy)
        # The adapter restores omitted defaults on load and refreshes the root
        # timestamp on save. Nested provenance timestamps should be preserved.
        expected["assumptions"]["global_defaults"]["recommended_emergency_months"] = 6
        expected["updated_at"] = "2026-10-02T10:00:00+00:00"
        with patch.object(state_adapter, "_timestamp", return_value=expected["updated_at"]):
            encoded = state_adapter.state_to_dict(decoded)
        self.assertEqual(encoded, expected)

    def test_unknown_persisted_fields_are_ignored(self):
        decoded = state_adapter.state_from_dict({"profile": {"accounts": [{
            "name": "Cash", "account_type": "Checking", "balance": 10,
            "future_field": "ignored",
        }]}, "future_top_level": True})
        self.assertEqual(decoded.profile.accounts[0].balance, 10)


class RentVsBuyCharacterizationTests(unittest.TestCase):
    def test_baseline_five_year_result_is_preserved(self):
        result = deterministic_run("Baseline", "US", horizon=5)
        self.assertAlmostEqual(result.summary["owner_net_worth"], 157407.040487574)
        self.assertAlmostEqual(result.summary["renter_net_worth"], 271768.80569762236)
        self.assertAlmostEqual(result.summary["net_worth_diff"], -114361.76521004835)

    def test_monte_carlo_is_reproducible_for_fixed_seed(self):
        kwargs = dict(
            scenario="Baseline", region="US", overrides=None, horizon=3,
            rent_basis="market", married=False, sell_at_end=True,
            n_sims=8, seed=1729, mc_profile="default",
            param_sd_scale=1.0, path_sd_scale=1.0,
        )
        first, _ = monte_carlo_run(**kwargs)
        second, _ = monte_carlo_run(**kwargs)
        pd.testing.assert_frame_equal(first, second)


if __name__ == "__main__":
    unittest.main()
