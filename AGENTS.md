# MoneyLab coding-agent guidance

## Project intent
MoneyLab is a financial research and decision-support platform. Calculations must remain transparent, reproducible, and clearly distinguished from financial advice.

## Architecture decisions
Design new components from approved product, architecture, design, and financial
methodology requirements. Evaluate legacy code against those requirements and
reuse it where it is correct, maintainable, and naturally aligned. Document
significant decisions to reuse, replace, or retire components. The legacy
Streamlit app may serve as a temporary reference and development safeguard.

## Current repository
- Existing application entry point: `app.py` (Streamlit).
- Shared state and helpers: `suite/`.
- Canonical analysis inputs: `moneylab/domain/` and `moneylab/configuration/`.
  See `docs/FINANCIAL_DOMAIN.md` for the authoritative contracts.
- Reusable, framework-independent financial code: `moneylab/engine/`.
- Canonical monthly execution: `moneylab/projection/`. See
  `docs/DETERMINISTIC_MONTHLY_PROJECTION.md` for the versioned methodology.
- Focused financial tools: `net_worth/`, `budget/`, `emergency_fund/`, `housing_affordability/`, and `rent_vs_buy/`.
- `STATE_ARCHITECTURE.md` describes the legacy Streamlit state adapter.
- The anticipated future stack is React/TypeScript + FastAPI + a Streamlit-independent Python financial engine. **Do not begin that migration unless it is explicitly in scope.**

## Working agreement
- Prefer bounded milestone work with documented scope and acceptance criteria.
- Create changes on feature branches; submit a pull request for review rather than merging into `main` yourself.
- Preserve the existing Streamlit application until a tested replacement exists.
- Avoid unrelated reformatting, dependency upgrades, or wholesale restructuring.
- Keep financial engine modules free of Streamlit, authentication, Supabase,
  credentials, network access, and implicit application state.
- Treat `suite.state` and `suite.calculations` as compatibility APIs; preserve
  persisted-state field names unless a reviewed migration is in scope.
- Never commit credentials, OAuth tokens, Supabase service keys, real user financial data, or local secrets. This repository may be publicly visible.
- Do not disable authentication or weaken production security to make tests pass. Development-only bypasses must be explicitly restricted.
- Keep guest access and user-controlled scenarios in mind when designing new architecture, but do not implement them outside the assigned milestone.
- Prefer concise, nonduplicative documentation. Explain only decisions needed to maintain or verify the code.

## Financial correctness
- Changes to calculation methods, timing conventions, taxes, simulation distributions, or accounting rules require explicit description and focused review.
- Preserve existing calculation behavior during refactors unless methodology changes are separately authorized.
- Add tests for boundaries and accounting identities, not just examples copied from the implementation.
- For stochastic models, support fixed seeds, documented assumptions and methodology, and comparable paths across scenarios where relevant.
- A passing test suite is necessary but not sufficient evidence of mathematical validity.

## Local checks
Use Python 3.11, matching the existing devcontainer:
```bash
python -m pip install -r requirements.txt
python -m compileall -q app.py moneylab suite budget emergency_fund housing_affordability net_worth rent_vs_buy assumptions
python -m unittest discover -s tests -v
```
The tests are intentionally small baseline safeguards. Do not claim full model validation from them.

## Handoff requirements
Every implementation PR should include: summary, scope, files changed, tests actually executed (and outcomes), known limitations, any effects on model methodology, and any manual review steps.
