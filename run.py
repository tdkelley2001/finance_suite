import argparse

from samplers.deterministic import deterministic_run
from samplers.monte_carlo import monte_carlo_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deterministic", "mc"], default="mc")
    parser.add_argument("--scenario", default="base")
    parser.add_argument("--region", default="US")
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--n_sims", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--param_unc", action="store_true")
    parser.add_argument("--path_unc", action="store_true")
    args = parser.parse_args()

    if args.mode == "deterministic":
        result = deterministic_run(args.scenario, args.region, overrides=None, horizon=args.horizon)
        print(result.summary)

    else:
        param_unc = args.param_unc or True
        path_unc = args.path_unc or True
        df, _ = monte_carlo_run(
            scenario=args.scenario,
            region=args.region,
            overrides=None,
            horizon=args.horizon,
            n_sims=args.n_sims,
            seed=args.seed,
            parameter_uncertainty=param_unc,
            path_uncertainty=path_unc,
            keep_yearly=False,
        )
        print(df.describe())
        print("Prob owner wins:", (df["net_worth_diff"] > 0).mean())


if __name__ == "__main__":
    main()