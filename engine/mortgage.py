import pandas as pd


def mortgage_schedule(assump):
    """
    Returns:
      schedule_df: year, mortgage_balance, principal_paid, interest_paid
      annual_mortgage_payment: constant annual payment (pmt * 12)
      loan_amount: original loan amount
    """
    loan_amount = assump.home_price * (1 - assump.down_payment_pct)
    r = assump.mortgage_rate / 12
    n = assump.mortgage_term * 12

    if r == 0:
        pmt = loan_amount / n
    else:
        pmt = loan_amount * r / (1 - (1 + r) ** -n)

    balance = loan_amount
    rows = []

    for year in range(1, assump.horizon + 1):
        interest = 0
        principal = 0

        for _ in range(12):
            i = balance * r
            p = pmt - i
            balance -= p
            interest += i
            principal += p

        rows.append(
            {
                "year": year,
                "mortgage_balance": balance,
                "principal_paid": principal,
                "interest_paid": interest,
            }
        )

    return pd.DataFrame(rows), pmt * 12, loan_amount
