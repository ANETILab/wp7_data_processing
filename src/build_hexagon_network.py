import polars as pl
import polars_h3 as plh3


def load_data_pl(i: int, res: int, path: str) -> pl.DataFrame:
    data = pl.read_parquet(f"{path}/{i:02x}.parquet")
    data = data.with_columns(
        plh3.latlng_to_cell(
            pl.col("latitude_mean"), pl.col("longitude_mean"), res, return_dtype=pl.Utf8
        ).alias(f"h3_{res}"),
        pl.col("interval_start").dt.to_string("%Y-%m-%d").alias("day"),
        pl.col("interval_start").dt.hour().alias("hour"),
    )

    data = data.sort("device_id", "interval_start", descending=[False, False])
    return data


def get_daily_stop_sequence_pl(seq: pl.DataFrame, hexagon_column: str) -> dict:
    transitions = (
        seq.select(
            [
                pl.col(hexagon_column).alias("src"),
                pl.col(hexagon_column).shift(-1).alias("dst"),
            ]
        )
        .filter(
            (pl.col("src") != pl.col("dst"))
            & pl.col("src").is_not_null()
            & pl.col("dst").is_not_null()
        )
        .group_by(["src", "dst"])
        .len()
    )

    result = {}

    for row in transitions.iter_rows(named=True):
        src, dst, count = row["src"], row["dst"], row["len"]

        result.setdefault(src, {})[dst] = count

    return result


def build_conncections(path: str, res: int, variant: str) -> pl.DataFrame:
    col = f"h3_{res}"
    connections = pl.DataFrame()
    for i in range(256):
        stops = load_data_pl(i, res, f"{path}/stops/{variant}")
        temp = (
            (
                stops.with_columns(
                    [pl.col(col).shift(-1).over(["device_id", "day"]).alias("target")]
                )
                .filter(
                    (pl.col(col) != pl.col("target")) & pl.col("target").is_not_null()
                )
                .group_by(["device_id", "day", "hour", col, "target"])
                .len()
            )
            .rename({col: "source", "len": "weight"})
            .sort(["device_id", "day", "hour"])
        ).with_columns(pl.col.day.str.to_date("%Y-%m-%d").dt.weekday().alias("dow"))
        connections = pl.concat([connections, temp])
        del stops

    return connections


def aggregate_by_trip(connections: pl.DataFrame) -> pl.DataFrame:
    return (
        connections.group_by(["source", "target"])
        .agg(pl.col("weight").sum())
        .sort("source", "target")
    )


def aggregate_by_device(connections: pl.DataFrame) -> pl.DataFrame:
    return (
        connections.group_by(["source", "target"])
        .agg(pl.col("device_id").unique().len().alias("weight"))
        .sort("source", "target")
    )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    import structlog
    import yaml

    log = structlog.get_logger()

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

    for variant in ["v1", "v2"]:
        for res in range(7, 11):
            log.info(f"processing variant {variant} / resolution {res}")
            path = f"{config['dirs']['output']}/{config['city']}"
            Path(f"{path}/hexagon_network/{variant}/{res}").mkdir(
                exist_ok=True, parents=True
            )
            connections = build_conncections(path, res, variant)
            connections.write_parquet(
                f"{path}/hexagon_network/{variant}/{res}/connections.parquet"
            )
            aggregate_by_trip(connections).write_csv(
                f"{path}/hexagon_network/{variant}/{res}/edges_trip.csv"
            )
            aggregate_by_device(connections).write_csv(
                f"{path}/hexagon_network/{variant}/{res}/edges_device.csv"
            )
