PARAM_META = {
    # --------------------------------------------------
    # Purchase & Financing
    # --------------------------------------------------
    "home_price": {
        "label": "Home price ($)",
        "kind": "currency",
        "group": "Purchase & Financing",
        "help": (
            "The total purchase price of the home. This is the starting value used to "
            "calculate your mortgage, down payment, property taxes, maintenance costs, "
            "and future appreciation."
        ),
    },
    "down_payment_pct": {
        "label": "Down payment (%)",
        "kind": "percent",
        "group": "Purchase & Financing",
        "help": (
            "The percentage of the home price you pay upfront in cash. A larger down "
            "payment reduces your mortgage balance and monthly payment, but requires "
            "more cash today."
        ),
    },
    "mortgage_rate": {
        "label": "Mortgage rate (%)",
        "kind": "percent",
        "group": "Purchase & Financing",
        "help": (
            "The annual interest rate on your mortgage loan. Higher rates increase your "
            "monthly payment and total interest paid over time."
        ),
    },
    "mortgage_term": {
        "label": "Mortgage term (years)",
        "kind": "int",
        "group": "Purchase & Financing",
        "help": (
            "How long you take to repay the mortgage. Common terms are 15 or 30 years. "
            "Longer terms lower monthly payments but increase total interest paid."
        ),
    },
    "closing_costs_pct": {
        "label": "Closing costs (%)",
        "kind": "percent",
        "group": "Purchase & Financing",
        "help": (
            "Upfront fees paid when buying the home, such as lender fees, title insurance, "
            "and legal costs. These are usually a percentage of the purchase price."
        ),
    },
    "pmi_rate": {
        "label": "PMI rate (%)",
        "kind": "percent",
        "group": "Purchase & Financing",
        "help": (
            "Private Mortgage Insurance (PMI) is an extra cost required if your down payment "
            "is small. It protects the lender, not you, and is typically removed once "
            "enough equity is built."
        ),
    },
    "pmi_ltv_cutoff": {
        "label": "PMI removal threshold (%)",
        "kind": "percent",
        "group": "Purchase & Financing",
        "help": (
            "The loan-to-value level at which PMI is removed. For example, 80% means PMI "
            "stops once your mortgage balance falls below 80% of the home’s value."
        ),
    },

    # --------------------------------------------------
    # Ongoing Owner Costs
    # --------------------------------------------------
    "maintenance_pct": {
        "label": "Maintenance (% of home value)",
        "kind": "percent",
        "group": "Ongoing Owner Costs",
        "help": (
            "Estimated annual cost of maintaining the home, such as repairs and upkeep. "
            "Often approximated as a percentage of the home’s value."
        ),
    },
    "property_tax_pct": {
        "label": "Property tax (%)",
        "kind": "percent",
        "group": "Ongoing Owner Costs",
        "help": (
            "Annual property tax rate charged by local governments, based on the value "
            "of the home. This typically increases as home values rise."
        ),
    },
    "hoa_monthly": {
        "label": "HOA fees (monthly $)",
        "kind": "currency",
        "group": "Ongoing Owner Costs",
        "help": (
            "Monthly homeowners association (HOA) fees, if applicable. These cover shared "
            "expenses like landscaping, amenities, or building maintenance."
        ),
    },
    "homeowners_insurance_annual": {
        "label": "Homeowners insurance (annual $)",
        "kind": "currency",
        "group": "Ongoing Owner Costs",
        "help": (
            "Annual insurance cost to protect the home against damage, disasters, and "
            "liability. This is required by most mortgage lenders."
        ),
    },
    "selling_costs_pct": {
        "label": "Selling costs (%)",
        "kind": "percent",
        "group": "Ongoing Owner Costs",
        "help": (
            "Costs paid when selling the home, such as real estate agent commissions and "
            "closing fees. These reduce the amount you receive when you sell."
        ),
    },

    # --------------------------------------------------
    # Rent Assumptions
    # --------------------------------------------------
    "monthly_rent": {
        "label": "Monthly rent ($)",
        "kind": "currency",
        "group": "Rent Assumptions",
        "help": (
            "The starting monthly rent. This is the baseline cost of renting in the first year."
        ),
    },
    "rent_growth_rate": {
        "label": "Rent growth rate (%)",
        "kind": "percent",
        "group": "Rent Assumptions",
        "help": (
            "How quickly rent is expected to increase each year. Higher values reflect "
            "tight rental markets or high inflation."
        ),
    },
    "renters_insurance_annual": {
        "label": "Renters insurance (annual $)",
        "kind": "currency",
        "group": "Rent Assumptions",
        "help": (
            "Annual cost of renters insurance, which covers personal belongings and liability "
            "but not the structure itself."
        ),
    },

    # --------------------------------------------------
    # Investment & Taxes
    # --------------------------------------------------
    "home_appreciation_rate": {
        "label": "Home appreciation rate (%)",
        "kind": "percent",
        "group": "Investment & Taxes",
        "help": (
            "Expected long-term annual growth in home value. This is uncertain and can vary "
            "widely by location and time period."
        ),
    },
    "capital_gains_tax_rate": {
        "label": "Capital gains tax rate (%)",
        "kind": "percent",
        "group": "Investment & Taxes",
        "help": (
            "Tax rate applied to gains when selling the home above the tax-free exclusion. "
            "Primary residences often receive favorable tax treatment."
        ),
    },
    "capital_gains_exclusion_single": {
        "label": "Capital gains exclusion ($)",
        "kind": "currency",
        "group": "Investment & Taxes",
        "help": (
            "The amount of home sale profit that is exempt from capital gains taxes for "
            "single filers. Married filers typically receive a higher exclusion."
        ),
    },
    "investment_return": {
        "label": "Investment return (%)",
        "kind": "percent",
        "group": "Investment & Taxes",
        "help": (
            "Expected annual return on investments, such as stocks or bonds, used to grow "
            "any cash not spent on housing."
        ),
    },
    "investment_tax_drag": {
        "label": "Investment tax drag (%)",
        "kind": "percent",
        "group": "Investment & Taxes",
        "help": (
            "Estimated reduction in investment returns due to taxes, such as dividends and "
            "capital gains. This lowers effective long-term growth."
        ),
    },
    "inflation": {
        "label": "Inflation rate (%)",
        "kind": "percent",
        "group": "Investment & Taxes",
        "help": (
            "General increase in prices over time. Inflation affects rent, wages, and costs, "
            "and reduces the purchasing power of money."
        ),
    },
}