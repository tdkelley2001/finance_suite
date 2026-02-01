# Budget & Cash Flow Tool

A simple, transparent budgeting model designed to answer one question clearly:

> Do I have monthly cash flow surplus, and how fragile is it?

This tool is part of the broader **Money Lab** personal finance modeling suite.

The Budget & Cash Flow Tool is intentionally:
- snapshot-based, not transactional
- editable and assumption-driven
- transparent rather than automated
- designed for clarity, not optimization theater

It is implemented as an interactive Streamlit application backed by a small, explicit modeling engine.

---

## Disclaimer

This tool is provided **for educational and exploratory purposes only**.

It is **not financial advice**, **not tax advice**, and **not a recommendation** to spend, save, invest, or allocate money in any particular way.

All outputs depend entirely on user-provided inputs and simplifying assumptions.  
You are responsible for how you interpret and use the results.

---

## Purpose and Scope

The Budget & Cash Flow Tool is designed to provide a **clean monthly snapshot** of income, expenses, savings, and remaining buffer.

It answers:
- how much income comes in each month
- how much goes out
- how much is explicitly saved
- what remains after those decisions

It does **not** attempt to track behavior or predict the future.

---

## What This Tool Is For

This tool is intended for users who:
- want a clear picture of monthly cash flow
- are planning major financial decisions (housing, savings, career changes)
- want to understand capacity rather than past behavior
- prefer explicit assumptions over automated categorization

---

## What This Tool Does Not Do

- It does not connect to bank accounts.
- It does not track historical transactions.
- It does not forecast future income or expenses.
- It does not optimize spending categories.
- It does not judge whether expenses are “good” or “bad.”

This tool models **structure**, not behavior.

---

## Core Concepts

### Monthly Cash Flow

The central output is **monthly buffer**, defined as:

Net Monthly Income
− Planned Savings
− Total Expenses
= Remaining Buffer


The remaining buffer represents income left after accounting for:
- explicitly planned savings, and
- all listed expenses.

A negative buffer indicates that spending and savings exceed income.

---

### Snapshot Model

Each budget represents a **point-in-time model**.

It answers:

> “If my life looked like this right now, what would my cash flow be?”

It does not answer:

> “What did I spend last month?”

---

### Planned Savings

Savings are treated as a **first-class use of cash**, not leftover money.

Examples include:
- retirement contributions
- brokerage transfers
- sinking funds
- planned cash reserves

Savings reduce available monthly buffer in the same way expenses do.

---

### Expenses as Prompts, Not Prescriptions

The tool initializes with a broad, exhaustive list of common expense categories.

Important design choices:
- all amounts default to zero
- all items default to not required
- categories exist to prompt thinking, not enforce structure

Users are expected to:
- remove rows that do not apply
- add rows that are missing
- mark required expenses explicitly

---

### Required vs Discretionary Expenses

Each expense can be marked as **required** or **discretionary**.

This distinction allows the model to report:
- total expenses
- required expenses
- discretionary expenses
- remaining buffer

The classification is entirely user-defined.

---

## Inputs

### Income
- Net monthly income is entered directly.
- Taxes are assumed to already be reflected in net income.

### Savings
- Planned monthly savings are entered explicitly.
- Savings are modeled as fixed monthly amounts.

### Expenses
- Expenses are entered in a table with:
  - category
  - subcategory
  - monthly amount
  - required flag
- Blank, null, or invalid values are treated as zero.

---

## Outputs

The tool produces a **monthly snapshot** including:
- total expenses
- required expenses
- discretionary expenses
- remaining buffer

These outputs are intended to:
- highlight margin of safety
- reveal fragility
- support downstream decision tools

---

## Save, Load, and Export

Budgets can be exported as CSV files.

Exports are:
- human-readable
- intentionally simple
- suitable for reuse or inspection outside the app

A blank template is also provided to support offline editing and uploads.

---

## Assumptions and Limitations

This tool intentionally simplifies reality.

Key limitations include:
- income is assumed stable over the modeled month
- timing of expenses within the month is ignored
- annual or irregular expenses must be manually annualized
- taxes are not modeled beyond net income inputs
- no behavioral adaptation is assumed

The goal is clarity, not realism.

---

## Design Principles

- **Transparency over automation**  
  All calculations are explicit and inspectable.

- **Assumptions over inference**  
  The model never guesses or categorizes spending.

- **Separation of concerns**  
  UI, data models, and calculations are cleanly separated.

- **Extensibility**  
  The model is designed to support future scenario and stress testing.

---

## Repository Structure (High Level)

```text
budget/
  app.py           # Streamlit UI
  defaults.py      # Starter expense categories
  engine.py        # Cash flow calculations
  models.py        # Domain data models
  io.py            # Import and export helpers

templates/
  budget_template.csv


## Intended Role in Money Lab

The Budget & Cash Flow Tool is foundational within the Money Lab suite.

It is designed to:
- stand on its own as a clear cash flow snapshot
- provide grounding for downstream decision tools
- surface fragility before optimization or forecasting

Many financial tools attempt to optimize without first establishing
whether a situation is stable.

This tool deliberately comes first.

It prioritizes **clarity and honesty** over precision or polish, and
serves as the cash flow backbone for future affordability, risk,
and planning models.