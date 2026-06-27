import pandas as pd
from suite.calculations import amortization_schedule, fixed_payment


def mortgage_schedule(assump):
    """
    Returns:
      schedule_df: year, mortgage_balance, principal_paid, interest_paid
      annual_mortgage_payment: constant annual payment (pmt * 12)
      loan_amount: original loan amount
    """
    loan_amount = assump.home_price * (1 - assump.down_payment_pct)

    schedule = amortization_schedule(
        principal=loan_amount,
        annual_rate=assump.mortgage_rate,
        term_years=assump.mortgage_term,
        horizon_years=assump.horizon,
    ).rename(columns={"balance": "mortgage_balance"})
    monthly_payment = fixed_payment(
        loan_amount,
        assump.mortgage_rate,
        assump.mortgage_term,
    )

    return pd.DataFrame(schedule), monthly_payment * 12, loan_amount
