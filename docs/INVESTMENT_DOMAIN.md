# Investment domain and exposure resolution

M04B1 defines investment inputs for canonical financial accounts.
`moneylab.investment.models` records investments, sleeves, and configuration.
`taxonomy` defines research exposures, `exposures` resolves a single monthly
return, `policy` validates policy inputs, and `resolve` creates a linked
investment input record. `portfolio` provides derived analytical groupings.
All modules use the standard library.

## Accounts, investments, and exposures

The [canonical account](FINANCIAL_DOMAIN.md) owns the financial valuation.
Multiple sleeves can describe that balance. They add no account positions
or net worth. A sleeve has an account-scoped ID, references an investment
model, and can link to a reported holding ID on that account. Each holding
can supply at most one sleeve. A sleeve without a holding can name a future
destination, an explicit residual treatment, or a hypothetical allocation.

An investment model can describe an asset-class investment without a security.
If supplied, a security has a namespace and an identifier, such as a ticker
in a named exchange or a vendor identifier in a vendor namespace. The
canonical holding's optional security label remains a reported fact. A sleeve's
explicit holding link associates it with the model. No identifier, account
classification, or tax treatment infers a modeled exposure or return.

The exposure taxonomy describes the economic exposure. The M04A
[economic path](ECONOMIC_PATHS.md) describes its modeled return. An explicit
mapping connects taxonomy IDs to series IDs. A security-specific series and
a broad-market modeling approximation are both possible with caller-supplied
inputs. The mapping is an assumption and does not establish the security's
actual performance or economic makeup.

## Taxonomy

The initial catalog is `moneylab-investment-exposures` version `1.0.0`.
Its records have stable IDs, labels, broad categories, and priority.

| Priority | Category | Stable exposure IDs |
| --- | --- | --- |
| Core | Equity | `us-equity-broad`, `developed-international-equity`, `emerging-market-equity` |
| Core | Fixed income | `us-treasury-short`, `us-treasury-intermediate`, `us-corporate-investment-grade`, `us-bond-aggregate` |
| Core | Cash | `cash` |
| Extended | Equity | `us-equity-large-cap`, `us-equity-mid-cap`, `us-equity-small-cap`, `us-equity-growth`, `us-equity-value` |
| Extended | Fixed income | `us-treasury-long`, `inflation-protected-bonds`, `us-corporate-high-yield`, `international-bonds` |
| Extended | Real estate and commodities | `public-real-estate`, `commodities` |

Core and extended describe research priority. The catalog supplies no
benchmarks, data, forecasts, or distribution parameters. Custom exposures
belong to an explicitly versioned taxonomy with IDs in the `custom.` namespace.
An unclassified amount can remain separately visible or receive an explicit
return treatment. Classification alone always supplies zero information
about expected returns.

Categories can overlap economically. Broad equity can contain small-cap,
large-cap, style, and real estate exposures. An aggregate bond allocation can
overlap Treasury and corporate exposures. Grouping by broad category sums
directly allocated values only. It never expands a direct index allocation
into implied components or treats those categories as independent risk factors.

## Opening allocation

`resolve_investments(snapshot, plan, ...)` uses the effective opening
account valuation. The supplied plan must reference that profile and fully
covered accounts in the financial subject's scope. Each account chooses one mode.

- **Aggregate** uses an explicit return for the whole account. Sleeve inputs
  and sleeve policies are excluded. Disclosed composition is unnecessary.
- **Detailed** links each reported holding to a sleeve, or uses a complete,
  explicitly hypothetical weight allocation over the modeled sleeves. It
  preserves the underlying holdings in the financial snapshot. An aggregate
  rate on the same account conflicts with this mode.

Reported monetary values remain fixed when an opening account override
increases its effective balance. Reported weights apply to the effective
total. Disclosed proportions are never normalized. The difference between
disclosed money and the account total remains an unclassified opening amount,
or moves into a dedicated residual sleeve with an explicit return treatment.
A modeled residual remains unclassified for portfolio reporting. A
hypothetical allocation replaces composition only for the analysis, never
the account valuation or factual holdings.

For weight-based openings, multiply the total by each supplied weight and by
any undisclosed fraction. Round each result down to the eight-place monetary
grid, then assign the leftover grid units to the largest fractional
remainders. Stable sleeve IDs break ties, with the unclassified bucket last
on a tie. Complete weights reconcile exactly with no balancing residual.
Unassigned monetary value stays unclassified. At zero opening value, the
modeled destinations and any declared weights remain visible. Derived current
weights are undefined. A target remains a future instruction.

## Return and cost inputs

A `ReturnTreatment` declares a nominal **total return** in the projection
currency. Price-only returns require an external transformation before use.
Foreign exposure requires total returns expressed in the projection currency.
The resolver does not translate currencies, add distributions, or infer a
hedging convention. The economic path supplies realized values. Currency and
cost basis are explicit assertions in the mapping today, with consistent
declarations required wherever a series is reused in the same resolution.

A direct mapping selects one investment return series. A fixed composite
selects multiple distinct series with positive weights summing to one.
`realized_return()` multiplies one month's observations by their explicit
weights and sums the products. A 60/40 mapping with +10% equities and −5%
bonds returns 4%. Each month's composite calculation uses the specified mix.
This approximation implies no ownership of the underlying pieces and makes
no claim about actual fund rebalancing or glide paths. A constant annual
effective return, including zero for static treatment, uses the existing
effective monthly conversion. Constant returns can name a taxonomy exposure
or stay unclassified.

`ReturnConvention.embedded_costs` is empty for gross total returns before
the modeled costs. Explicit `fund_expense` and `advisory_fee` flags record
which costs the return already includes. Fund expenses can be supplied on
the investment and advisory fees on the account. A positive separate charge
conflicts with the same embedded cost. An advisory fee on the whole account
also conflicts if that fee is embedded in any of the account's treatments.

For M04B2, the proposed separate fee fraction is
`1 - (1 - annual_fee_fraction) ** (1 / 12)`. The proposal applies the
deduction to post-return investment value before month-end financial
activity. Billing and real fund accrual can differ. M04B1 performs no fee
deductions or expense postings.

## Policy records

Target weights describe modeled destinations. They cover every sleeve and
sum to one. Zero is valid and differs from an omitted weight. Opening
allocations remain unchanged when a target is specified. A future destination
may start with zero value. Policy revisions identify fixed instructions and
leave room for later dated targets.

- **Contributions** can use target, current, rebalancing-directed, or custom
  weights. Current allocation at zero balance needs explicit fallback weights
  for readiness. The proposed rebalancing-directed method minimizes squared
  dollar deviations from post-contribution targets, allocating the full
  contribution without selling investments.
- **Withdrawals** can use proportional, rebalancing-directed, cash-first,
  or custom weights. Cash-first names a modeled cash-exposed sleeve and a
  non-cash-first secondary policy. Explicit allocations specify the intended
  sleeves and do not authorize redirection if one lacks funds. Choosing an
  account for funding is a separate question from selling investments within
  it. Policy validity conveys no legal withdrawal eligibility.
- **Rebalancing** supports none, calendar, threshold, calendar or threshold,
  and threshold evaluation on scheduled dates. Dates are month-ends of
  explicitly named months each calendar year. Absolute drift measures
  percentage points of allocation. Relative drift divides the deviation by
  target weight. For zero targets a relative rule must specify any positive
  weight or a separate absolute threshold. A future triggered rebalance would
  restore target weights.

The three policies compose independently. M04B1 validates their input
requirements. Actual policy algorithms and all trading are deferred to
M04B2 or later.

## Grouping, precedence, and reproduction

`PortfolioGroup` is an analytical set of existing account IDs. Groups can
overlap and each account appears only once within a group. Multiple groups
cannot be added together as independent holdings. The summary counts the
known account totals and reports unknown-valued accounts separately. Unknown
value makes the group total unknown. Known zero remains explicit. Exposure
amounts use explicitly modeled detailed sleeves and composite exposure
weights. Bare holdings and aggregate assumptions do not imply taxonomy-level
allocation. Unknown and unclassified amounts stay visible, and weights are
derived only for a fully valued, positive group. Hypothetical accounts are
identified in the summary.

Only local analysis and saved investment scenarios can override opening
composition or investment policy. A saved investment scenario references the
existing financial scenario revision and the applicable plan ID. Local
overrides win field by field. Return treatments use local, saved scenario,
personal investment plan, selected return-only preset, and explicitly
supplied research-default precedence. Presets and defaults fill treatments
for already modeled targets and cannot replace holdings, allocations, or
policy. No forecasts or default allocations are bundled.

The immutable resolved input records the financial snapshot ID and schema,
taxonomy, relevant investment and sleeve identities, valuation and allocation
sources, opening values, policy and return origins, modeled fees, and selected
path ID and schema when applicable. It uses schema 1 and the MoneyLab
canonical JSON and SHA-256 content identity convention. Retain the actual
financial snapshot and path with the resolved investment input for replay.
`validate_investment_sources()` checks these references, the account opening
values, and referenced return series after reloading inputs.
A ticker, catalog label, result hash, or revision alone cannot reproduce
an observation. Investment inputs are linked records and leave the financial
snapshot schema unchanged.

Structural validity allows incomplete holdings and balances. Resolution
checks the applicable scope, links, mappings, currencies, amounts, and
policy requirements. Resolved inputs may retain execution blockers.
`require_ready()` flags unassigned opening money, stale valuations, and
current-allocation contributions without a zero-balance fallback. Future
execution must still check supported policies, legal access, available
funding, and the financial inputs using the shared executor.

## Validation and M04B2 boundary

`tests/test_investment_domain.py` covers independent opening-dollar, composite
return, portfolio-group, cost, policy, and scenario cases. M04B2 must carry
end-of-month sleeve balances forward, compute returns from evolving sleeve
dollars, resolve fee and activity effects, and reconcile the sum of sleeves
to the authoritative account at the shared monthly posting boundary. Fixed
opening weights cannot substitute for evolving values. M04B3 and later
methodologies can extend policy behavior using explicit dated inputs.
