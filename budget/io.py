import pandas as pd
from budget.models import BudgetProfile

def budget_to_dataframe(profile: BudgetProfile) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Category": e.category,
                "Subcategory": e.subcategory,
                "Monthly Amount": e.monthly_amount,
                "Required": e.required,
            }
            for e in profile.expenses
        ]
    )
