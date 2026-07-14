import polars as pl


def read_stops(stop_detection_variant: str) -> pl.DataFrame:
    stops = pl.DataFrame()
    for i in range(256):
        part = pl.read_parquet(
            f"{config['dirs']['output']}/{config['city']}/stops/{stop_detection_variant}/{i:02x}.parquet"
        )
        stops = pl.concat([stops, part])
    return stops


if __name__ == "__main__":
    from pathlib import Path
    import yaml
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="config file (YAML)",
    )
    parser.add_argument(
        "--stop-detection-variant",
        type=str,
        required=True,
        help="stop detection variant",
    )
    opts = parser.parse_args()

    with open(opts.config, "r") as fp:
        config = yaml.safe_load(fp)

    stops = read_stops(opts.stop_detection_variant).with_columns(
        pl.col.interval_start.dt.to_string("%Y-%m").alias("year_month")
    )

    for p in stops.partition_by("year_month"):
        path = f"{config['dirs']['output']}/{config['city']}/monthly_partitioned_stops/{opts.stop_detection_variant}/"
        Path(path).mkdir(exist_ok=True, parents=True)
        p_ = p.sort(["device_id", "interval_start"]).drop("year_month")
        p_.write_parquet(f"{path}/{p['year_month'].first()}.parquet")

        del p_
