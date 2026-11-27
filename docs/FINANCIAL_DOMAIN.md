# Canonical financial domain and configuration

## Package boundaries and use

- `moneylab.domain.profile` contains current financial facts. `domain.planning`
  describes intended activity, goals, and scheduled changes. `domain.values`
  defines money, dates, provenance, and revision conventions.
- `moneylab.configuration` defines typed analysis requests, economic assumptions,
  model preferences, presets, scenarios, and the resolver. Its snapshot is the
  input boundary for future calculation engines. Calculated metrics and projected
  states belong to those engines' outputs.
- Both packages use only the Python standard library. For existing calculators,
  `moneylab.engine.calculations` remains a source of tested financial primitives.
  The standalone loan example verifies the existing fixed-payment primitive at
  an explicit Decimal-to-float and whole-year conversion boundary. The
  canonical layer does not import it.
- The Streamlit models in `moneylab.engine.models` and `suite.state` continue to
  serve the [legacy application](../STATE_ARCHITECTURE.md). They are independent
  of this contract. Existing profile storage and tool execution use their
  original interfaces.

## Financial facts and relationships

| Record | Purpose and relationships |
| --- | --- |
| Person and household | A profile can store multiple people and one optional household with explicit membership. People outside the household can be owners, obligors, or beneficiaries. A projection selects a person or household by ID. Birth date is optional. |
| Account | Holds an authoritative dated valuation and independently records legal account classification, tax treatment, access restrictions, holdings, and beneficiaries. |
| Non-account asset | Records its own valuation, classification, and legal owners. It has no dependency on how tools group or display that asset. |
| Liability | Records the outstanding value and responsible people. Optional terms include current annual nominal interest rate, fixed or variable rate type, and maturity date. A liability may have no rate, schedule, or maturity information. |
| Ownership | References one or more people. Shares can all be unknown or all be specified as positive fractions totaling one. Beneficiaries and household membership convey no legal ownership. |

IDs are explicit, case-sensitive strings. Names can change independently of IDs.
The profile validates person references and enforces unique position IDs across
accounts, assets, and liabilities. Holding IDs are scoped to their account.
Plan and scenario records have their own ID and caller-managed revision. Plan
activity, goal, and event IDs are unique within their respective categories.

Store a jointly owned position once. `positions_for(subject)` returns each
participating position once, including its full ownership record.
`Ownership.share_within()` reports the group's share when it is known. A group
covering all legal owners has a full share even when the internal split is
unknown. A partial group with unknown shares gets `None`. This API inventories
and describes positions. Any future aggregate must apply the appropriate
ownership basis. Each legal owner must be in the profile's people roster.
Entity ownership, beneficiary rights, and dated membership history are deferred.

Account holdings describe part or all of the authoritative account valuation
as of the same date. A holding has either a nonnegative value in the account
currency or a weight from 0 to 1, plus an asset class and optional security ID.
Use one basis per account. Disclosed values require a known total and cannot
exceed it. Weight totals cannot exceed 1 and can exist before an account value
is available. An unreported remainder is unclassified. Cash is identified
only by an explicit cash holding. Holdings have no separate balance-sheet
value. Aggregate balances, net worth, and savings rates are derived outputs.

## Values and timing

- Money and rates use finite `Decimal` values with at most 18 integer places
  and 8 fractional places. Construction validates precision without rounding.
  Rates, ownership shares, and weights are fractions. An annual rate of 5% is
  `Decimal("0.05")`. Annual economics permit negative rates above −100%.
- Positions and planned amount magnitudes are nonnegative. An activity's type
  and accounts give it direction. Zero is an explicit value. `None` on a
  valuation represents an unknown amount. A known valuation requires a date.
- A profile and associated plan use a single currency. Currency values are
  three uppercase letters with no code registry or exchange-rate service.
  Mixed currencies are rejected. A standalone request has its own currency.
- Dates are calendar dates without times or time zones. Activity periods
  include `start_on` and exclude `end_before`, with no end when absent.
  Frequencies describe the period of the stated amount. M03 will define
  occurrence expansion, intra-month timing, proration, and monthly rate
  conversion.

## Financial plans

A plan references a profile by ID. Its records use person or household subjects.
Tracked funding accounts and liabilities must exist and relate to that subject.
A household analysis selects its own activity plus activity assigned to its
members. Individual analyses select activity assigned directly to that person.

External income can credit a tracked account and external expenses can debit
one. Either can be recorded without an account reference. Transfers,
contributions, and withdrawals move value between two distinct tracked
accounts. They do not create external household income or expense. A direct
external deposit is recorded as income to its destination account. Debt payments
reference a liability and can identify a funding account. An optional split
must equal principal plus interest. Principal reduces the balance and interest
is an economic expense. An absent split remains unknown.

A goal defines a target amount, target date, subject, and optional funding
accounts. A scheduled change sets the prospective amount of an existing income
or expense from its effective date within the activity period. Each activity
allows one change per date. An override changes the base recurring amount.
The saved scheduled change becomes applicable on its date.

## Configuration and analysis readiness

Resolution accepts specific typed inputs. Economic assumption fields are
annual inflation and annual investment return. Model preferences are the
projection horizon in months and whether results use real dollars.

| Eligible inputs | Precedence, highest to lowest |
| --- | --- |
| Economic assumptions and model preferences | Local analysis override → saved scenario override → selected preset → explicitly supplied research defaults |
| In-scope recurring amount | Local analysis override → saved scenario override → baseline plan |
| Profile facts, ownership, plan routes, dates, and scheduled changes | Baseline records supplied by the caller |

Configuration field `None` is equivalent to omission and falls through.
An activity amount must be explicit money. Zero and false take precedence
like any other specified value. Unsupported fields, duplicate overrides,
debt payment overrides, unknown or out-of-scope activities, and currency
mismatches are rejected. A preset can supply economic or model fields only.
There is one selected preset. Competing selections fail if the supplied preset
ID conflicts with the scenario. Illustrative presets and research defaults
exist only in tests. There are no bundled economic defaults.

A scenario stores a profile ID, optional constraining plan and preset IDs,
its revision, and its overrides. The caller supplies live records including
their actual revisions. When a plan or preset ID is absent from the scenario,
the caller may still supply one. No loader runs during resolution. All such
inputs remain independent and changes are expressed through replacement records.

Structural validation covers field types, amounts, ownership and cross-record
references. Partial profiles can still have missing optional information.
Empty collections enumerate supplied records and carry no assertion of catalog
completeness. Required missing projection inputs raise `MissingAnalysisInput`.
Standalone loan input requires only principal, rate, and a term in months.
It rejects scenario and profile context. The initial monthly projection
contract requires a valid subject, a first-of-month start date, a horizon,
and known valuations dated on or before the start for participating positions.
An explicit real-dollar preference also requires inflation. Optional assumptions
stay unset if unavailable. This validates the input contract only. M03 still
needs model-specific checks for missing return assumptions, opening valuation
alignment, legal-share attribution, and debt payment treatment.

## Snapshot lifecycle and reproducibility

`resolve_analysis()` returns a frozen `ResolvedAnalysis`. The snapshot
captures the requested analysis type and inputs, the supplied profile, the
effective plan, assumptions and preferences, and revisions of the profile,
plan, scenario, preset, and defaults where applicable. Projection snapshots
keep the full supplied baseline as reference context. Engines select their
scope using the recorded subject. Activity-amount provenance identifies which
layer supplied the effective value. Assumptions and preferences also identify
their source. Facts, goals and events keep their provenance on their records.
Methods and external data revisions, seed, and path count are captured when
the caller supplies them. No projection method or dataset revision is bundled.

Snapshots use frozen records and privately captured tuples on construction.
Replacing a source profile, plan or preset produces new input records and
does not change previous snapshots. The schema-versioned JSON contract
round-trips through the same validation and rejects unknown fields, duplicate
JSON keys, and unsupported versions. Canonical JSON sorts object keys and
uses compact separators, ISO dates, Decimal strings with insignificant trailing
zeros removed, and stable ID order for unordered record collections. The
content ID is SHA-256 over that JSON encoded as UTF-8. Equivalent snapshots
have the same recorded values and metadata, including revision IDs, provenance,
scope, and seed. Input order and equivalent decimal spelling do not change
the ID. A revision change can change the ID even when model values are equal.

This provides input reproducibility. Rerunning a historical calculation also
requires its actual implementation, compatible runtime, and external dataset
contents. Those execution and storage systems are outside this milestone.

## Executable examples

`python -m unittest discover -s tests -v` runs the synthetic examples in
`tests/test_canonical_domain.py` and `tests/test_configuration.py`. They cover
the standalone loan request, one-person and joint household positions and
plans, saved and temporary overrides, source revisions, and snapshot replay
through serialization.
