# Economic paths and monthly execution

M04A supplies immutable economic inputs for a single projection. The
standard-library `moneylab.economics` package defines observations and how
to construct paths. `moneylab.projection.path_execution` maps observations
to financial positions and invokes the shared M03 monthly executor.

## Observations, construction, and time alignment

An `EconomicPath` contains named series, one observation for every declared
series in each month, and construction metadata. Series are independent of
the financial snapshot. For example, a series named `equity` can be used by
two accounts or by entirely different scenarios.

| Series kind | Realized monthly value |
| --- | --- |
| `investment_return` | Simple effective fractional return on opening value. A value of `0.02` means a 2% gain for that month. A value of `-1` removes the entire opening value. Later inflows can restore it. Lower values are rejected. |
| `inflation` | Simple effective fractional change in the price level. At most one inflation series supplies the purchasing-power basis. It must be greater than `-1` in every month. |

Observations use finite Decimals with up to 18 integer and 60 fractional
places. The integer envelope follows the canonical inputs and bounds the
representation. Extra fractional precision preserves the M03 rate conversion.
The monetary range and rounding of actual growth and postings remain the
[M03 financial rules](DETERMINISTIC_MONTHLY_PROJECTION.md).

Periods are chronological, unique, and contiguous. Each begins on the first
of a calendar month and ends exclusively on the first of the next month. The
first and last boundaries identify the opening date and end of the path. Every
month has exactly the declared series, including explicit zero observations.
An empty series catalog is valid for a path with only explicit constant
treatments and no inflation.

- Construct an explicit path with `EconomicSeries`, `EconomicMonth`,
  `EconomicObservation`, and `PathMetadata`. The caller supplies a versioned
  construction method and may identify a versioned source.
- `constant_path()` constructs monthly observations from a complete set of
  `AnnualRate` inputs. It uses the same effective-rate conversion and Decimal
  context as M03. Its methodology and annual generation assumptions are
  recorded separately from the realized monthly values.

An execution requires the path start and horizon to match the financial
snapshot exactly. Use `path.subpath(start_on, end_before)` for a shorter or
later calendar interval. The slice retains those exact months and identifies
its immediate parent by content ID. Selecting the full interval returns
the same path. Missing months and observations fail validation. The engine
never remaps calendar dates, interpolates observations, or silently truncates
or extends the path.

## Exposures and execution readiness

`project_economic_path(snapshot, path, exposures)` takes an explicit
`PositionExposure` for each in-scope account or non-account asset. Every
exposure names an investment series or supplies its own annual effective
rate. An explicit annual rate of zero selects static treatment. Mapping the
same series to many positions is supported. Liabilities use the existing debt
rules. They cannot take a return exposure.

An exposure keyed to a series consumes the monthly observation directly.
Explicit annual rates on exposures use the shared effective-rate conversion.
If the financial snapshot already supplies deterministic growth for a
position, only an explicit identical annual exposure can coexist with it.
Series mappings and different rates conflict. A run can omit all snapshot
growth entries when exposures supply complete coverage. The general
investment assumption remains contextual.

Path runs require resolved annual inflation to be unset in the financial
snapshot. This avoids two competing sources. A constant path can record its
annual inflation assumption in path construction metadata. If there is a
monthly inflation series, the driver starts the index at one at the analysis
opening and multiplies by each month's realized factor. Real-dollar reporting
requires this complete series. A run without inflation can produce nominal
output. Each subpath uses its own opening purchasing-power basis.

Path driver methodology is `realized-economic-path-monthly-projection`
version `1.0.0`. The shared financial methodology is
`deterministic-monthly-projection` version `1.0.0`. Explicit methodology
requests must match the driver. Stochastic execution settings on a financial
request are unsupported here. Optional seed, path index, algorithm, and
parameter revision in path metadata describe the origin of an already
realized input. This entry point performs no random generation.

After readiness and path validation, the driver supplies each month's
position rates and inflation factor to the common loop. The same monthly
executor handles postings, debt, funding, atomic settlement, and
reconciliation for both drivers. `project_monthly()` preserves the M03
interface and serialized result format. Invalid economic inputs raise
`EconomicPathError` before execution. Financial readiness errors,
range exceptions, reconciliation failures, and modeled funding or debt stops
remain distinct. A modeled stop can reflect a funding route or settlement
constraint even when the modeled household has other wealth.

## Identity and reproducibility

Path schema 1 supports canonical JSON round trips with sorted keys, ISO
dates, and normalized Decimal strings. Series and observations are sorted by
ID and months retain calendar order. The path content ID is the SHA-256 hash
of that JSON, including observations and provenance. The same realized values
with different provenance have different IDs. No separate observation-only
hash is used.

`PathProjectionResult` schema 1 wraps the financial projection and an
execution reference. The reference records the financial snapshot and
economic path content IDs and schema versions, the exact sorted exposures,
and the financial, execution, and path methodology revisions.
`execution_content_id` hashes that canonical reference. It can be derived
from the `execution` record in JSON. The nested projection reports its actual
driver methodology. The nested annual-growth field records only explicit
annual exposures. Realized growth and inflation are represented by the
retained path and mappings.

To replay an execution, retain the financial snapshot, the selected realized
path, the effective exposure records, and a compatible implementation of
their referenced methodologies. The result does not embed the entire path.
A seed, source name, or method label by itself does not reproduce the path.
Scenarios can use the same path ID with different financial snapshots or
exposures. Slices can share identical observations during overlapping months
even though their full path and execution identities differ.

## Validation and next interface

`tests/test_economic_paths.py` compares equivalent constant-path and M03
results, including debt, financing stops, effects, and inflation. It checks
variable paths independently. An opening balance of $1,000 exposed to +10% and
−20% closes at $880 in either order with no flows. With $100 month-end deposits,
the two orders close at $1,060 and $1,090. A shared series drives independent
account balances without sharing their contributions or withdrawals.

The [M04B1 investment domain](INVESTMENT_DOMAIN.md) validates investment
inputs and resolves a single sleeve's direct, composite, or constant return.
The M04A financial path driver still accepts direct and constant position
exposures. M04B2 will use evolving sleeve values at the shared posting
boundary. Historical dataset conventions, stochastic generation, and
simulation summaries have their own future work packages.
