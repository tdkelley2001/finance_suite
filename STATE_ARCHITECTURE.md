# Shared State Architecture

Money Lab state is split into four top-level buckets.

## 1. Profile

The user's current financial life. This should be reusable across tools and
should not represent a what-if case.

Current profile areas:

- `monthly_cash_flow`: current income, required expenses, discretionary
  expenses, planned savings, minimum monthly buffer.
- `accounts`: cash, brokerage, retirement, HSA, 529, and other account balances.
- `balance_sheet`: total assets, total liabilities, net worth, liquid assets,
  retirement assets, and taxable assets.
- `assets`: home, vehicles, business interests, and other non-account assets.
- `liabilities`: mortgage, student loans, credit cards, auto loans, and other
  debt.
- `goals`: emergency fund, retirement, home purchase, education, debt payoff,
  and other named user goals.

Ownership guidance:

- Budget owns monthly cash flow.
- Net Worth owns accounts, balance sheet, assets, and liabilities.
- A future Goals tool should own profile-level goals.
- Other tools may read profile data and may suggest changes, but should not
  silently overwrite another tool's owned profile area.

## 2. Assumptions

Suite-wide modeling defaults. These are not the user's current life; they are
default modeling knobs used by calculators unless a scenario overrides them.

Examples:

- inflation
- expected portfolio return
- expected portfolio volatility
- tax rates
- default withdrawal rate
- default planning horizon
- default housing appreciation and rent growth assumptions

## 3. Scenarios

Named what-if cases. Scenarios can store tool inputs and assumption overrides.
The active scenario is `Current` by default.

Examples:

- `Current`
- `Retire at 55`
- `Buy house in 2028`
- `High inflation`
- `Lower savings rate`

## 4. Tool Outputs

Summarized outputs from calculators. These are meant for dashboards and
cross-tool reuse. They should be compact, structured summaries, not full UI
render state.

Examples:

- budget buffer
- affordability max home price
- rent-vs-buy net worth difference
- retirement probability of success
- emergency fund target
- emergency fund coverage months and gap/surplus

## Provenance Rule

Every profile field that can be reused across tools should carry provenance:

- `source_type`: `manual`, `tool`, `import`, or `system`
- `source_id`: tool key or import source
- `label`: human-readable source label
- `updated_at`: timestamp

This lets the UI explain where a value came from, for example:

`Net monthly income came from Budget on 2026-06-21.`

The suite should prefer explicit ownership over implicit overwrites. If a tool is
not the owner for a profile area, it should either read the value, write a
scenario-specific input, or produce a tool output.
