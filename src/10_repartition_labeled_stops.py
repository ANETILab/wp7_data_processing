import polars as pl


def join_stops_with_home_labels(path: str, stop_detection_variant: str) -> pl.DataFrame:
    # join infostop stops with HoWDe home/work/other labels across all 256 hex partitions.
    parts = []
    for i in range(256):
        stops_lf = pl.scan_parquet(
            f"{path}/stops/{stop_detection_variant}/{i:02x}.parquet"
        )
        howde_lf = pl.scan_parquet(
            f"{path}/howde/{stop_detection_variant}/{i:02x}_howde.parquet"
        )

        part = stops_lf.join(
            howde_lf.select(
                ["useruuid", pl.col("loc").cast(pl.Int32), "location_type"]
            ),
            left_on=["device_id", "stop_id"],
            right_on=["useruuid", "loc"],
            how="left",
        ).collect()
        parts.append(part)

    return pl.concat(parts)


if __name__ == "__main__":
    import argparse
    import yaml
    from pathlib import Path

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

    # join infostop stops with HoWDe home/work/other labels across all 256 hex partitions.
    stops = join_stops_with_home_labels(
        f"{config['dirs']['output']}/{config['city']}",
        opts.stop_detection_variant,
    )

    stops = stops.with_columns(
        pl.col.interval_start.dt.to_string("%Y-%m").alias("year_month")
    )

    # sort once, then write one parquet per calendar month.
    out_dir = Path(
        f"{config['dirs']['output']}/{config['city']}/monthly_partitioned_stops/{opts.stop_detection_variant}_labeled"
    )
    out_dir.mkdir(exist_ok=True, parents=True)

    for year_month, p in (
        stops.sort(["year_month", "device_id", "interval_start"])
        .partition_by("year_month", as_dict=True, maintain_order=True)
        .items()
    ):
        p.drop("year_month").write_parquet(out_dir / f"{year_month[0]}.parquet")
