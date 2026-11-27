"""Baseline financial checks; not comprehensive model validation."""

import unittest

from suite.calculations import cash_flow_snapshot, compound_value, fixed_payment


class CalculationBasicsTests(unittest.TestCase):
    def test_zero_rate_loan_amortizes_evenly(self):
        self.assertAlmostEqual(
            fixed_payment(12_000, annual_rate=0, term_years=1), 1_000.0
        )

    def test_mortgage_payment_matches_independent_formula(self):
        # Standard fixed-rate amortizing loan, monthly compounding.
        principal = 200_000
        rate = 0.06 / 12
        periods = 30 * 12
        expected = principal * rate * (1 + rate) ** periods / ((1 + rate) ** periods - 1)
        self.assertAlmostEqual(fixed_payment(principal, 0.06, 30), expected, places=7)

    def test_reject_invalid_loan_term(self):
        with self.assertRaises(ValueError):
            fixed_payment(1_000, annual_rate=0.05, term_years=0)

    def test_cash_flow_reconciles(self):
        cash_flow = cash_flow_snapshot(
            income=5_000, required_expenses=2_000,
            discretionary_expenses=1_000, savings=500,
        )
        self.assertEqual(cash_flow.total_expenses, 3_000)
        self.assertEqual(cash_flow.buffer, 1_500)

    def test_compound_value_with_variable_returns(self):
        # 100 -> 110 -> 99. Arithmetic average returns would be incorrect here.
        self.assertAlmostEqual(compound_value(100, [0.10, -0.10]), 99.0)


if __name__ == "__main__":
    unittest.main()
