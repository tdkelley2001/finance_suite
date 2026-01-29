def values_equal(a, b, tol=1e-6):
    if a is None or b is None:
        return a == b
    try:
        return abs(a - b) < tol
    except TypeError:
        return a == b
    

def format_assumption_value(val, kind):
    if kind == "currency":
        return f"${val:,.0f}"
    elif kind == "percent":
        return f"{val:.2%}"
    elif kind == "int":
        return f"{int(val)}"
    else:
        return str(val)


def highlight_overrides(row):
    if row["Overridden"]:
        return ["background-color: #4A587A"] * len(row)
    return [""] * len(row)