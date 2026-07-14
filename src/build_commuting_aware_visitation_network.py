import polars as pl


def determine_visitation_network(
    connections: pl.DataFrame, home_work: pl.DataFrame, res: int
) -> pl.DataFrame:
    m = connections.join(home_work, on="device_id")
    from_home = m.filter(
        (pl.col("source") == pl.col("home")) & (pl.col("target") != pl.col("work"))
    )
    from_work = m.filter(
        (pl.col("source") == pl.col("work")) & (pl.col("target") != pl.col("home"))
    )

    result = pl.DataFrame()
    result = pl.concat([result, from_home])
    result = pl.concat([result, from_work])
    return result


def aggregate_by_trip(
    visitations: pl.DataFrame, home_work: pl.DataFrame
) -> pl.DataFrame:
    return (
        visitations.join(home_work, on="device_id")
        .group_by(["home", "work", "source", "target"])
        .agg(pl.sum("weight"))
    )


def aggregate_by_device(
    visitations: pl.DataFrame, home_work: pl.DataFrame
) -> pl.DataFrame:
    return (
        visitations.join(home_work, on="device_id")
        .group_by(["home", "work", "source", "target"])
        .agg(pl.col("device_id").unique().len().alias("weight"))
    )


def filter_connections(df: pl.DataFrame, filtering: dict) -> pl.DataFrame:
    result = df.clone()
    if filtering["from_date"]:
        result = result.filter(pl.col.hour >= filtering["from_date"])
    if filtering["to_date"]:
        result = result.filter(pl.col.hour < filtering["to_date"])
    if len(filtering["days_of_week"]) > 0:
        result = result.filter(pl.col.dow.is_in(filtering["days_of_week"]))
    if filtering["from_hour"]:
        result = result.filter(pl.col.hour >= filtering["from_hour"])
    if filtering["to_hour"]:
        result = result.filter(pl.col.hour < filtering["to_hour"])
    return result


if __name__ == "__main__":
    from pathlib import Path
    import yaml
    import argparse
    import shutil

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="config file (YAML)",
    )
    parser.add_argument(
        "--visitation-network-config",
        type=str,
        required=True,
        help="stop detection config file (YAML)",
    )
    opts = parser.parse_args()

    with open(opts.config, "r") as fp:
        config = yaml.safe_load(fp)

    with open(opts.visitation_network_config, "r") as fp:
        vn_config = yaml.safe_load(fp)

    path = f"{config['dirs']['output']}/{config['city']}"

    for res in range(7, 11):
        for by in ["device", "trip"]:
            hw = pl.read_parquet(
                f"{path}/homes/{vn_config['stop_detection_variant']}/home_work_h3_{res}.parquet"
            )
            hw = hw.rename({f"h3_{res}_home": "home", f"h3_{res}_work": "work"})
            hw = hw.drop_nulls()

            hw = hw.filter(
                (
                    pl.col("count_home")
                    > vn_config["filtering"]["minimum_stops_for_home"]
                )
                & (
                    pl.col("count_work")
                    > vn_config["filtering"]["minimum_stops_for_work"]
                )
            )

            connections = pl.read_parquet(
                f"{path}/hexagon_network/{vn_config['stop_detection_variant']}/{res}/connections.parquet"
            )
            connections = filter_connections(connections, vn_config["filtering"])
            visitations = determine_visitation_network(connections, hw, res=res)
            aggregated = aggregate_by_trip(visitations, hw)
            if by == "device":
                aggregated = aggregate_by_device(visitations, hw)

            aggregated = aggregated.sort(["home", "work", "source", "target"])

            out_path = f"{path}/visitation_network/{vn_config['home_detection']}/{vn_config['stop_detection_variant']}/{by}/{vn_config['variant']}"
            Path(out_path).mkdir(exist_ok=True, parents=True)
            shutil.copy(
                "09_visitation_network_config.yaml",
                f"{out_path}/visitation_network_config.yaml",
            )
            aggregated.write_csv(f"{out_path}/{res}.csv")
            aggregated.write_parquet(f"{out_path}/{res}.parquet")

    # runs 1m 45s
