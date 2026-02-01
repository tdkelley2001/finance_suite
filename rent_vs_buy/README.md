# Rent vs Buy Model

A deterministic and Monte Carlo–based financial model for comparing the long-run net worth outcomes of **renting versus owning a home**, under configurable economic scenarios, regional assumptions, and uncertainty regimes.

This tool is part of the broader **Money Lab** personal finance modeling suite.

The model is designed to be:
- transparent
- reproducible
- extensible
- decision-supportive (not prescriptive)

---

## Disclaimer

This model is provided **for educational and exploratory purposes only**.

It is **not financial advice**, **not investment advice**, and **not a recommendation** to rent, buy, sell, or hold any asset.

Key limitations to keep in mind:
- Results are **highly sensitive to assumptions**. Small changes in inputs can materially change outcomes.
- Scenarios and Monte Carlo simulations represent **hypothetical futures**, not forecasts or predictions.
- The model simplifies reality and omits many real-world considerations (liquidity constraints, credit availability, behavioral factors, local tax nuances, transaction frictions, personal risk tolerance, and life events).
- Outputs should be interpreted as **decision-support illustrations**, not point estimates or guarantees.

You are solely responsible for how you interpret and use the results. Consider consulting qualified professionals before making real financial decisions.

---

## Who This Tool Is For

This model is intended for users who:
- are deciding between renting and buying a primary residence
- want to understand long-run tradeoffs, not just monthly payments
- are comfortable exploring assumptions and ranges of outcomes
- care about downside risk and uncertainty, not just averages

---

## What This Tool Does Not Do

- It does not determine what home you can afford.
- It does not optimize mortgage structures or refinancing strategies.
- It does not capture lifestyle preferences or psychological utility.
- It does not predict the future or assign probabilities to real outcomes.

---

## Core Question

> *Under a given set of assumptions, what is the distribution of long-run net worth outcomes for renting versus owning?*

Rather than producing a single “answer,” the model explicitly separates:
- baseline assumptions,
- structural economic uncertainty, and
- path-level volatility.

This allows users to explore **ranges of outcomes**, tail risk, and sensitivity to assumptions.

---

## Model Structure

The model is organized into three conceptual layers.

---

### 1. Deterministic Baseline

Given:
- an economic **scenario**
- a geographic **region**
- optional **parameter overrides**
- a time **horizon**

the deterministic engine produces:
- yearly cash flows
- asset values
- liabilities
- net worth paths for owner and renter

This layer answers:

> *“What happens if the world evolves exactly as assumed?”*

---

### 2. Monte Carlo Uncertainty Layer

The Monte Carlo engine wraps the deterministic model and introduces uncertainty in two distinct ways.

#### Parameter Uncertainty (Structural)

Long-run averages such as:
- investment returns
- home appreciation
- rent growth
- inflation

are sampled once per simulation to reflect uncertainty about the *true* economic environment.

#### Path Uncertainty (Volatility)

Year-to-year randomness is applied to:
- asset returns
- housing appreciation
- rent growth
- inflation

to reflect realistic economic noise over time.

Each simulation represents a **plausible alternate future**, not a forecast.

---

### 3. UI and Configuration Layer

All assumptions are controlled externally via:
- scenario YAML files
- region YAML files
- optional user overrides
- Monte Carlo profiles and scaling controls

The modeling engine itself contains **no hard-coded UI logic**.

---

### Model Regime Controls

Certain assumptions are treated as **structural model choices**, not numeric overrides.

Examples include:
- rent basis
- filing status (single versus married)
- whether the home is sold at the end of the horizon

These controls:
- are set explicitly in the UI
- are not stored in scenario or region YAMLs
- override any baseline defaults
- are always visible in the Active Assumptions summary

This distinction preserves clarity between:
- *how the model works*, and
- *what values it uses*.

---

## Assumptions and Limitations

This model intentionally simplifies reality in order to make tradeoffs explicit and analyzable.

### Economic and Market Assumptions
- Long-run rates (investment returns, home appreciation, rent growth, inflation) are modeled as stationary within a scenario, even though real economies experience regime shifts.
- Monte Carlo simulations represent plausible futures, not forecasts or probability-weighted predictions of actual outcomes.
- Correlations between economic variables are simplified and may not fully capture real-world dynamics.

### Housing and Financing Simplifications
- Mortgage terms are assumed to remain fixed as specified.
- Refinancing, recasting, and renegotiation are not modeled.
- Credit constraints and underwriting frictions are excluded.
- Liquidity risk and the inability to access home equity when needed are not explicitly priced.

### Taxes and Legal Nuance
- Tax treatment is modeled at a high level.
- Jurisdiction-specific deductions, credits, and timing effects may not be fully reflected.
- Changes in tax law over time are not modeled.

### Behavioral and Life Factors (Not Modeled)
- Job mobility, family changes, health events, and preference shifts are excluded.
- Psychological utility such as stability or flexibility is not quantified.
- Forced sales, foreclosures, and distress scenarios are not explicitly simulated.

### Interpretation Guidance
- Outputs should be interpreted **comparatively**, not as absolute truth.
- The model is best used to understand **sensitivity, tradeoffs, and risk distributions**, not to produce a single “correct” decision.

---

## Key Concepts

### Scenarios

Scenarios define coherent macroeconomic environments such as base, disinflation, or high inflation.

They specify:
- baseline growth rates
- inflation regimes
- return assumptions

Scenarios are defined in `scenarios.yaml`.

---

### Regions

Regions apply geographic tilts such as:
- home price growth
- rent growth
- property tax levels
- insurance costs

Regions are defined in `regions.yaml`.

---

### Rent Basis

The model supports multiple definitions of renter housing costs in the first year.

| Rent Basis | Description |
|-----------|-------------|
| `market` | Uses the region’s baseline market rent |
| `match_mortgage` | Sets year-1 rent equal to the owner’s annual mortgage payment |
| `match_owner_cost` | Sets year-1 rent equal to the owner’s full housing cost (mortgage, taxes, maintenance, insurance, HOA) |

Matching applies **only in year one**.  
After year one, rent evolves independently based on rent growth assumptions.

This design isolates the effect of initial affordability while allowing realistic long-run divergence.

---

### Overrides

Any baseline parameter can be overridden at runtime.

Overrides:
- default to scenario and region values
- apply only when explicitly set
- are always visible in the UI

This mirrors spreadsheet-style override cells while preserving a clean baseline.

---

### Monte Carlo Profiles

Monte Carlo behavior is controlled via profiles that define the intensity of uncertainty.

| Profile | Description |
|--------|-------------|
| Baseline | Moderate uncertainty consistent with long-run averages |
| Conservative | Lower volatility and tighter distributions |
| Volatile | Elevated uncertainty and dispersion |
| Stress | Extreme uncertainty and tail risk |

Profiles act as presets. Sliders allow fine-tuning within each regime.

---

## Outputs

### Deterministic Mode
- Net worth over time (owner versus renter)
- Final net worth comparison
- Economic decomposition
- Full yearly detail table

### Monte Carlo Mode
- Distribution of net worth differences
- Probability that owning outperforms renting
- Median, downside, and upside outcomes
- Tail behavior under stress

---

## Design Principles

- **Separation of concerns**  
  Deterministic logic, uncertainty modeling, and UI are cleanly separated.

- **Immutability and reproducibility**  
  Distributions are immutable. Randomness is controlled via explicit seeds.

- **Auditability**  
  Active assumptions are always visible and traceable.

- **Extensibility**  
  New scenarios, regions, or uncertainty regimes can be added without modifying core logic.

---

## Repository Structure (High Level)

```text
engine/
  assumptions.py        # Scenario and region resolution
  yearly_model.py       # Deterministic yearly simulation
  mortgage.py           # Mortgage mechanics
  rate_provider.py      # Deterministic versus stochastic rate paths

samplers/
  deterministic.py     # Deterministic runner
  monte_carlo.py       # Monte Carlo wrapper
  distributions.py     # Immutable distribution definitions

ui/
  app.py               # Streamlit application
  sections.py          # Output sections and charts
  sidebar_assumptions.py
  run_summary.py

scenarios.yaml         # Economic scenarios
regions.yaml           # Regional assumptions