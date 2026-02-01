import pandas as pd


def get_default_expenses_df() -> pd.DataFrame:
    """
    Returns an exhaustive but neutral starter list of common monthly expenses.
    All amounts default to 0 and all items are marked as not required.
    """
    rows = [

        # -----------------------
        # Housing
        # -----------------------
        ("Housing", "Rent / Mortgage"),
        ("Housing", "Property taxes"),
        ("Housing", "Home / renter’s insurance"),
        ("Housing", "HOA"),
        ("Housing", "Utilities (electric / gas / water)"),
        ("Housing", "Internet"),
        ("Housing", "Mobile phone"),
        ("Housing", "Maintenance / repairs"),
        ("Housing", "Furnishings"),

        # -----------------------
        # Food
        # -----------------------
        ("Food", "Groceries"),
        ("Food", "Dining out"),
        ("Food", "Coffee / takeout"),
        ("Food", "Alcohol"),

        # -----------------------
        # Transportation
        # -----------------------
        ("Transportation", "Car payment"),
        ("Transportation", "Gas"),
        ("Transportation", "Auto insurance"),
        ("Transportation", "Maintenance"),
        ("Transportation", "Parking / tolls"),
        ("Transportation", "Public transit"),
        ("Transportation", "Rideshare"),

        # -----------------------
        # Insurance (non-auto)
        # -----------------------
        ("Insurance", "Health insurance"),
        ("Insurance", "Dental / vision insurance"),
        ("Insurance", "Life insurance"),
        ("Insurance", "Disability insurance"),

        # -----------------------
        # Healthcare (out of pocket)
        # -----------------------
        ("Healthcare", "Prescriptions"),
        ("Healthcare", "Doctor visits"),
        ("Healthcare", "Therapy"),
        ("Healthcare", "Medical supplies"),

        # -----------------------
        # Subscriptions & tech
        # -----------------------
        ("Subscriptions", "Streaming services"),
        ("Subscriptions", "Software / apps"),
        ("Subscriptions", "Cloud storage"),
        ("Subscriptions", "News / media"),

        # -----------------------
        # Personal & lifestyle
        # -----------------------
        ("Personal", "Clothing"),
        ("Personal", "Personal care"),
        ("Personal", "Gym / fitness"),
        ("Personal", "Hobbies"),
        ("Personal", "Entertainment"),
        ("Personal", "Travel fund"),

        # -----------------------
        # Family & obligations
        # -----------------------
        ("Family", "Childcare"),
        ("Family", "Tuition"),
        ("Family", "Child support"),
        ("Family", "Elder care"),
        ("Family", "Gifts / holidays"),

        # -----------------------
        # Financial
        # -----------------------
        ("Financial", "Credit card payments"),
        ("Financial", "Student loans"),
        ("Financial", "Other debt"),
        ("Financial", "Professional fees"),

        # -----------------------
        # Miscellaneous
        # -----------------------
        ("Miscellaneous", "Charitable giving"),
        ("Miscellaneous", "Irregular expenses"),
        ("Miscellaneous", "Other"),
    ]

    return pd.DataFrame(
        [
            {
                "Category": category,
                "Subcategory": subcategory,
                "Monthly Amount": 0.0,
                "Required": False,
            }
            for category, subcategory in rows
        ]
    )
