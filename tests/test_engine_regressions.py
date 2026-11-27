"""Characterization tests for behavior preserved during the M01 extraction."""

import sys
import unittest

import pandas as pd

from moneylab.engine.models import (
    Asset, FinancialAccount, Liability, MonthlyCashFlowState, UserState,
)
from rent_vs_buy.samplers.deterministic import deterministic_run
from rent_vs_buy.samplers.monte_carlo import monte_carlo_run
from suite.state import state_from_dict, state_to_dict


class EngineBoundaryTests(unittest.TestCase):
    def test_engine_import_does_not_load_streamlit_or_supabase(self):
        # Remove modules loaded by suite.state above, then import in an isolated process-like state.
        for name in list(sys.modules):
            if name == "moneylab" or name.startswith("moneylab."):
                del sys.modules[name]
        for name in ("streamlit", "supabase"):
            sys.modules.pop(name, None)
        __import__("moneylab.engine")
        self.assertNotIn("streamlit", sys.modules)
        self.assertNotIn("supabase", sys.modules)

    def test_suite_state_types_are_compatibility_reexports(self):
        from suite.state import FinancialAccount as LegacyFinancialAccount
        self.assertIs(LegacyFinancialAccount, FinancialAccount)


class PersistedStateCompatibilityTests(unittest.TestCase):
    def test_round_trip_preserves_existing_shape_and_nested_types(self):
        state = UserState()
        state.profile.monthly_cash_flow = MonthlyCashFlowState(net_monthly_income=7_500)
        state.profile.accounts = [FinancialAccount("Cash", "Checking", 4_000)]
        state.profile.assets = [Asset("Car", "Vehicle", 12_000)]
        state.profile.liabilities = [Liability("Loan", "Auto Loan", 6_000, 300, 0.05)]
        encoded = state_to_dict(state)
        decoded = state_from_dict(encoded)
        self.assertEqual(decoded.profile.monthly_cash_flow.net_monthly_income, 7_500)
        self.assertEqual(decoded.profile.accounts[0], state.profile.accounts[0])
        self.assertEqual(decoded.profile.assets[0], state.profile.assets[0])
        self.assertEqual(decoded.profile.liabilities[0], state.profile.liabilities[0])

    def test_unknown_persisted_fields_are_ignored(self):
        decoded = state_from_dict({"profile": {"accounts": [{
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
