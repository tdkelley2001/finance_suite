# Rent vs Buy Model

A deterministic and Monte Carlo–based financial model for comparing the long-run net worth outcomes of **renting vs owning a home**, under configurable economic scenarios, regional assumptions, and uncertainty regimes.

The model is designed to be:
- transparent
- reproducible
- extensible
- decision-supportive (not prescriptive)

It is implemented as both:
- a Python modeling engine, and
- an interactive Streamlit application.

---

## Core Question

> *Under a given set of assumptions, what is the distribution of long-run net worth outcomes for renting vs owning?*

Rather than producing a single “answer,” the model explicitly separates:
- baseline assumptions,
- structural economic uncertainty, and
- path-level volatility.

This allows users to explore **ranges of outcomes**, tail risk, and sensitivity to assumptions.

---

## Model Structure

The model is organized into three conceptual layers:

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
The Monte Carlo engine wraps the deterministic model and introduces uncertainty in two distinct ways:

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

### 3. UI / Configuration Layer
All assumptions are controlled externally via:
- scenario YAML files
- region YAML files
- optional user overrides
- Monte Carlo profiles and scaling controls

The modeling engine itself contains **no hard-coded UI logic**.

---

## Key Concepts

### Scenarios
Scenarios define coherent macroeconomic environments (for example: base, disinflation, high inflation).

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

### Overrides
Any baseline parameter can be overridden at runtime.

Overrides:
- default to scenario + region values
- apply only when explicitly set
- are fully visible in the UI

This mirrors spreadsheet-style “override cells” while preserving a clean baseline.

---

### Monte Carlo Profiles
Monte Carlo behavior is controlled via **profiles**, which define the *intensity* of uncertainty:

| Profile | Description |
|------|------------|
| Baseline | Moderate uncertainty consistent with long-run averages |
| Conservative | Lower volatility and tighter distributions |
| Volatile | Elevated uncertainty and dispersion |
| Stress | Extreme uncertainty and tail risk |

Profiles act as presets. Sliders allow fine-tuning within each regime.

---

## Outputs

### Deterministic Mode
- Net worth over time (owner vs renter)
- Final net worth comparison
- Economic decomposition (waterfall)
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

- **Immutability & reproducibility**  
  Distributions are immutable. Randomness is controlled via explicit seeds.

- **Auditability**  
  Active assumptions are always visible and traceable.

- **Extensibility**  
  New scenarios, regions, or uncertainty regimes can be added without changing core logic.

---

## Repository Structure (High Level)

```text
engine/
  assumptions.py        # Scenario + region resolution
  yearly_model.py       # Deterministic yearly simulation
  mortgage.py           # Mortgage mechanics
  rate_provider.py      # Deterministic vs stochastic rate paths

samplers/
  monte_carlo.py        # Monte Carlo wrapper
  deterministic.py     # Deterministic runner
  distributions.py     # Immutable distribution definitions

app.py                 # Streamlit application
scenarios.yaml         # Economic scenarios
regions.yaml           # Regional assumptions