from pathlib import Path

import polars as pl
import polars_distance as pld


def calculate_distance(data: pl.DataFrame) -> pl.DataFrame:
    return (
        data.with_columns(
            pl.col("latitude")
            .shift()
            .over("device_id", order_by="timestamp")
            .alias("prev_latitude"),
            pl.col("longitude")
            .shift()
            .over("device_id", order_by="timestamp")
            .alias("prev_longitude"),
        )
        .with_columns(
            pl.struct(
                pl.col("latitude").alias("latitude"),
                pl.col("longitude").alias("longitude"),
            ).alias("current_point"),
            pl.struct(
                pl.col("prev_latitude").alias("latitude"),
                pl.col("prev_longitude").alias("longitude"),
            ).alias("previous_point"),
        )
        .with_columns(
            pld.col("current_point")
            .dist.haversine("previous_point", unit="km")
            .alias("distance_km")
        )
        .with_columns(
            pl.col("timestamp")
            .diff()
            .over("device_id", order_by="timestamp")
            .alias("time_diff")
        )
    )


if __name__ == "__main__":
    import argparse

    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="config file (YAML)",
    )
    opts = parser.parse_args()

    with open(opts.config, "r") as fp:
        config = yaml.safe_load(fp)

    DIR = f"{config['dirs']['output']}/{config['city']}/partitioned"

    Path(f"{DIR}/with_speed/").mkdir(exist_ok=True, parents=True)
    for i in range(128, 256):
        df = pl.read_parquet(f"{DIR}/{i:02x}/pings.parquet")
        df = calculate_distance(df)
        df = df.with_columns(
            (pl.col.distance_km * 1000 / pl.col.time_diff.dt.total_seconds()).alias(
                "speed_mps"
            )
        )
        df.drop(
            [
                "prev_latitude",
                "prev_longitude",
                "current_point",
                "previous_point",
                "id_with_type",
            ],
            strict=False,
        ).write_parquet(f"{DIR}/with_speed/{i:02x}.parquet")
