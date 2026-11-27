"""Independent financial reference cases and accounting identities."""

import math
import unittest

from budget.engine import calculate_budget_summary
from budget.models import BudgetAssumptions, BudgetExpense, BudgetProfile, SavingsItem
from emergency_fund.engine import EmergencyFundInputs, calculate_emergency_fund
from housing_affordability.engine import (
    cash_required_for_price,
    housing_cost_from_price,
    max_payment_from_constraints,
)
from housing_affordability.models import (
    AffordabilityConstraints,
    CashPosition,
    Household,
    MortgageAssumptions,
)
from moneylab.engine.calculations import amortization_schedule, fixed_payment
from moneylab.engine.models import Asset, FinancialAccount, Liability
from net_worth.engine import calculate_balance_sheet


class BalanceSheetCorrectnessTests(unittest.TestCase):
    def test_balance_sheet_reconciles_and_classifies_accounts(self):
        result = calculate_balance_sheet(
            [
                FinancialAccount("Checking", "Checking", 10_000),
                FinancialAccount("Brokerage", "Taxable Brokerage", 25_000),
                FinancialAccount("401k", "401(k)", 40_000),
                FinancialAccount("Roth", "Roth IRA", 15_000),
                FinancialAccount("HSA", "HSA", 5_000),
            ],
            [Asset("Home", "Home", 300_000)],
            [Liability("Mortgage", "Mortgage", 200_000)],
        )
        self.assertEqual(result.total_assets, 395_000)
        self.assertEqual(result.total_liabilities, 200_000)
        self.assertEqual(result.net_worth, result.total_assets - result.total_liabilities)
        self.assertEqual(result.liquid_assets, 35_000)
        self.assertEqual(result.retirement_assets, 55_000)
        self.assertEqual(result.taxable_assets, 25_000)


class CashFlowCorrectnessTests(unittest.TestCase):
    def test_budget_categories_and_cash_flow_reconcile(self):
        profile = BudgetProfile(
            assumptions=BudgetAssumptions(
                net_monthly_income=6_000,
                savings=[SavingsItem("401k", 600), SavingsItem("IRA", 200)],
            ),
            expenses=[
                BudgetExpense("Housing", "Rent", 2_000, True),
                BudgetExpense("Food", "Groceries", 500, True),
                BudgetExpense("Fun", "Dining", 300, False),
            ],
        )
        result = calculate_budget_summary(profile)
        self.assertEqual(result.total_expenses, 2_800)
        self.assertEqual(result.required_expenses, 2_500)
        self.assertEqual(result.discretionary_expenses, 300)
        self.assertEqual(result.buffer, 2_400)
        self.assertAlmostEqual(result.savings_rate, 800 / 6_000)
        self.assertEqual(result.expense_breakdown_by_category["Food"], 500)

    def test_zero_income_has_zero_savings_rate(self):
        result = calculate_budget_summary(BudgetProfile())
        self.assertEqual(result.savings_rate, 0.0)


class EmergencyFundCorrectnessTests(unittest.TestCase):
    def test_required_expense_target_and_coverage(self):
        result = calculate_emergency_fund(EmergencyFundInputs(
            monthly_required_expenses=3_000, monthly_total_expenses=4_000,
            monthly_net_income=6_000, cash_balance=12_000,
            liquid_assets=18_000, recommended_months=6,
        ))
        self.assertEqual(result.target_emergency_fund, 18_000)
        self.assertEqual(result.current_coverage_months, 4)
        self.assertEqual(result.liquid_asset_coverage_months, 6)
        self.assertEqual(result.gap_surplus, -6_000)

    def test_zero_expenses_do_not_divide_by_zero(self):
        result = calculate_emergency_fund(EmergencyFundInputs(
            0, 0, 0, 1_000, 2_000, 6,
        ))
        self.assertEqual(result.current_coverage_months, 0)


class LoanAndHousingCorrectnessTests(unittest.TestCase):
    def test_amortization_reconciles_principal_and_ends_at_zero(self):
        principal = 120_000
        schedule = amortization_schedule(principal, 0.06, 10, 10)
        self.assertAlmostEqual(schedule["principal_paid"].sum(), principal, places=6)
        self.assertAlmostEqual(schedule.iloc[-1]["balance"], 0.0, places=6)

    def test_payment_matches_closed_form(self):
        principal, annual_rate, years = 300_000, 0.065, 30
        rate, periods = annual_rate / 12, years * 12
        expected = principal * rate / (1 - math.pow(1 + rate, -periods))
        self.assertAlmostEqual(fixed_payment(principal, annual_rate, years), expected)

    def test_housing_constraints_and_cost_components(self):
        mortgage = MortgageAssumptions(0.06, 30, 0.012, 1_200, 100, 0.01)
        cash = CashPosition(100_000, 0.10, 0.03, 10_000)
        cost = housing_cost_from_price(300_000, mortgage, cash)
        self.assertAlmostEqual(cost.principal_and_interest, fixed_payment(270_000, 0.06, 30))
        self.assertEqual(cost.property_tax, 300)
        self.assertEqual(cost.insurance, 100)
        self.assertEqual(cost.hoa, 100)
        self.assertEqual(cost.pmi, 225)
        self.assertEqual(cash_required_for_price(300_000, cash), 49_000)
        household = Household(8_000, 3_000, 1_000, 500)
        self.assertEqual(max_payment_from_constraints(
            household, AffordabilityConstraints(0.30)), 2_400)


if __name__ == "__main__":
    unittest.main()
