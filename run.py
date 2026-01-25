import argparse

from samplers.deterministic import deterministic_run
from samplers.monte_carlo import monte_carlo_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deterministic", "mc"], default="mc")
    parser.add_argument("--scenario", default="base")
    parser.add_argument("--region", default="US")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--rent_basis", choices=["market", "match_mortgage", "match_owner_cost"], default="market")
    parser.add_argument("--married", action="store_true", default=False)
    parser.add_argument("--sell_at_end", action="store_true", default=True)
    parser.add_argument("--n_sims", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mc_profile", choices=["Baseline", "Conservative", "Volatile", "Stress"], default="Baseline")
    parser.add_argument("--param_sd_scale", type=float, default=1.0)
    parser.add_argument("--path_sd_scale", type=float, default=1.0)
    args = parser.parse_args()

    if args.mode == "deterministic":
        result = deterministic_run(
            args.scenario,
            args.region,
            overrides=None,
            horizon=args.horizon,
            rent_basis=args.rent_basis,
            married=args.married,
            sell_at_end=args.sell_at_end,
        )
        print(result.summary)

    else:
        df, _ = monte_carlo_run(
            scenario=args.scenario,
            region=args.region,
            overrides=None,
            horizon=args.horizon,
            rent_basis=args.rent_basis,
            married=args.married,
            sell_at_end=args.sell_at_end,
            n_sims=args.n_sims,
            seed=args.seed,
            mc_profile=args.mc_profile,
            param_sd_scale=args.param_sd_scale,
            path_sd_scale=args.path_sd_scale,
            keep_yearly=False,
        ) 
        print(df.describe())
        print("Prob owner wins:", (df["net_worth_diff"] > 0).mean())


if __name__ == "__main__":
    main()