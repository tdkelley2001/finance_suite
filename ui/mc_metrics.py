def summarize_net_worth_diff(df):
    return {
        "prob_owner_wins": (df["net_worth_diff"] > 0).mean(),
        "median": df["net_worth_diff"].median(),
        "p10": df["net_worth_diff"].quantile(0.10),
        "p90": df["net_worth_diff"].quantile(0.90),
    }