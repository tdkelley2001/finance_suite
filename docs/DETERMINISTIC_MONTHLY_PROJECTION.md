# Deterministic monthly financial projection

Methodology `deterministic-monthly-projection` version `1.0.0`.
Result schema version 1.

## Inputs and execution readiness

The engine projects supplied single-currency positions and activity over
complete calendar months. An empty collection describes the supplied model
and carries no assertion about real-world completeness. The
[canonical domain contract](FINANCIAL_DOMAIN.md) defines the resolved input.
Projection uses effective opening valuations, the resolved plan, and explicit
assumptions. It records the actual methodology and snapshot content ID.
Conflicting methodology versions, other analysis types, and stochastic
settings are rejected.

Every effective opening valuation must fall exactly on the projection start
date. Earlier valuations require an aligned input or a permitted hypothetical
valuation override. Zero is valid. Each account and non-account asset needs
an explicit annual effective growth rate, with zero for a static position.
Account type, tax treatment, holdings, and the general investment assumption
do not determine growth.

An individual must wholly own or be wholly responsible for selected
positions. A household must contain all owners or obligors of each selected
position. Joint positions contained in the household appear once, even if
shares are unspecified. Legal responsibility for joint debt can differ from
pro-rata economic ownership. Partial positions require later attribution
rules. Activity assigned outside the subject that overlaps the horizon and
affects a selected position is a readiness error. Selected activity also
cannot reference positions outside the boundary.

## Timeline and activity

The result has a distinct opening observation. Each monthly period spans
`[start_on, end_before)`. The closing observation at the next month boundary
becomes the next period's opening state. Execution follows this order.

1. Select monthly activities active on the opening date. The start is
   inclusive and the end is exclusive. The latest scheduled income or expense
   change effective on or before the opening sets the month's amount.
2. Apply growth and accrue loan interest on opening balances.
3. Credit named external income at month-end, quote debt payments, and test
   whether each source account can fund all its planned debits.
4. Settle month-end debits, reconcile closing positions and net worth, and
   carry balances forward.

Overlapping activities require monthly frequency and first-of-month starts
and ends. Applicable scheduled changes require first-of-month dates. Weekly,
biweekly, annual, and partial-month schedules require a later methodology.
Nominal amounts are used as supplied. No escalation, proration, withholding,
or tax calculation is applied.

External income requires a named destination. Expenses and debt payments
require a named source. Transfers, contributions, and withdrawals debit one
account and credit another. A debit account must have explicit unrestricted
access and be either a modeled deposit with no reported noncash holdings or
an account whose opening balance is fully covered by disclosed cash holdings.
For non-deposits, cash weights must sum to one or cash holding values must
equal the effective opening balance. This prevents implicit liquidation.
Modeled routes confer no statutory eligibility. Penalties, contribution
limits, and withdrawal exceptions are outside this methodology.

## Growth and inflation

The monthly equivalent of annual effective rate `r` is
`(1 + r)^(1/12) - 1`. Apply it to the opening balance and round the product
once per month for the gain or loss. Non-account asset growth uses a separately
supplied rate under the same conversion. Positive and negative rates above
−100% are supported. Month-end inflows begin earning in the following month.
Account growth applies to the total. Holdings-level growth is deferred.

The result's `position_growth` lists the effective annual rates used for
position growth. Its optional `annual_inflation` records the rate used for
the reporting index. A resolved general `annual_investment_return` remains
context in the input snapshot and its content ID. It supplies no M03
growth rate and is absent from the result's consumed inputs.

When supplied, annual inflation is effective. The index starts at 1 and
compounds monthly. Optional real net worth is nominal net worth divided by
that index, in opening-date purchasing power. Inflation changes no nominal
postings or reconciliation.

## Fixed-rate debt

Positive debt requires a mortgage or installment loan, fixed terms, and an
explicit nonnegative nominal annual rate. At most one payment can be active
per liability per month. For opening balance `B`, annual nominal rate `j`,
and planned payment `P`, rounded interest is `I = round(B × j / 12)`.
The payable amount is `min(P, B + I)`. Interest is paid first and the
remainder reduces principal. A payment below interest or a lack of payment
when rounded interest is positive stops the month. Interest-only payments
and static zero-rate balances are supported.

If supplied, an explicit split must agree with the rounded interest and
principal for every active month with positive debt, including the capped
final payment. Payment above the payoff amount is never debited. Extinguished
debt accrues no interest and subsequent payments are skipped.

An in-horizon maturity must fall on a month boundary after opening. The
liability must be extinguished by the closing observation on that boundary.
An unpaid balance stops execution there. The engine supplies no balloon
payment, accrued arrears, interest capitalization, or revolving, variable-rate,
refinancing, or delinquency treatment.

## Funding, effects, and reconciliation

Available funds are the source account's opening balance after growth plus
credited external income. Incoming internal movements cannot fund same-month
debits under this initial settlement rule. Total requested debits are tested
together per account, so activity IDs or input order do not assign priorities.
A shortfall or servicing issue
leaves the entire attempted month unposted, including tentative growth,
income, and interest. The result preserves the last reconciled observation
and records the attempted period, planned amounts, and either servicing
issues or grouped deficits. Deficits identify the account, available funds,
required funds, and competing debits. Unpaid expenses remain unmet. The model
creates no cash overdraft, receivable, liability, or automatic funding route.

A stop can reflect the supplied funding policy or modeled routes even when
the household has wealth elsewhere. Future retirement and integrated
projections will need explicit policies that route eligible withdrawals and
transfers into the accounts paying expenses in the same period. Those policies
will need explicit ordering and reconciliation of each movement.

| Applied effect | Position postings | Economic net-worth effect |
| --- | --- | --- |
| External income or expense | Increase destination or decrease funding balance | Signed amount |
| Transfer, contribution, or withdrawal | Decrease source and increase destination equally | Zero |
| Account return or asset revaluation | Signed change to the position | Signed amount |
| Debt interest accrued | Increase outstanding debt | Negative interest |
| Debt interest paid | Decrease cash and accrued debt equally | Zero |
| Debt principal paid | Decrease cash and principal equally | Zero |

Monthly effects identify the period through their parent record and include
amount, signed postings, and activity ID where applicable. Each nonnegative
closing balance must equal its opening balance plus the sum of its postings.
Net worth is accounts and assets less liabilities. The engine checks this
aggregate independently against opening net worth plus income, less external
expenses and accrued debt interest, plus signed growth. Unexpected failures
raise a reconciliation exception.

Calculations use a 60-digit Decimal context. Monthly growth and interest
round half to even at eight fractional places. Planned amounts fit that
grid. Postings and nominal reconciliation use exact grid arithmetic with
zero residual. Rounded monetary effects, reported balances, and nominal and
real net worth must be finite and have magnitude below 10^30. This existing
limit keeps modeled amounts on the eight-place grid and leaves headroom for
exact posting arithmetic. It is a bound on calculated money. Growth and
inflation inputs retain their canonical domain validation.

The inflation index must stay finite and positive. Numerical boundary failures
raise `ProjectionRangeError`, with the attempted month and affected value when
applicable. This is an execution error distinct from a modeled funding stop.
Reconciliation errors still surface independently. Real net worth is rounded
for reporting. Monthly rounding can cause small differences from unrounded
references.

## Integration boundary for economic paths

`project_monthly()` is the deterministic driver. It converts annual assumptions
to monthly rates once, supplies the same realized growth rates each period, and
advances the cumulative inflation index from one. The existing `_execute_month`
boundary receives realized monthly growth rates keyed by position and the
cumulative index at the closing boundary. It owns postings, fixed-rate debt,
funding checks, atomic settlement, and reconciliation.

The [economic path driver](ECONOMIC_PATHS.md) supplies period-specific monthly
rates and inflation factors to the same loop and settlement logic. M03's
deterministic entry point and result format are unchanged.

## Independent validation

`tests/test_monthly_projection.py` checks closed-form growth, month-end
contributions, and a fixed-rate remaining balance formula, alongside
hand-calculated cash flows and transfers. Examples include $1,000 at 12%
effective reaching approximately $1,120 after 12 months, $12,000 at 6%
nominal accruing $60 in month one, and $1,200 nominal after one year of 2%
inflation equaling $1,176.47058824 in opening dollars. The 360-month reference
allows small monthly rounding drift. Another test introduces offsetting
position errors that would pass an aggregate-only net-worth check.
Boundary cases cover large growth and debt interest, 360 months near the
negative annual rate limit, and real net worth crossing the reporting bound
while nominal projections remain valid.
