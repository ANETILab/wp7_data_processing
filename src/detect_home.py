import geopandas as gpd
import polars as pl
import polars_h3 as plh3
import yaml
from datetime import datetime


def detect_home_work(
    data: pl.DataFrame,
    config: dict,
    spatial_id: str = "h3",
    device_id: str = "device_id",
) -> pl.DataFrame:
    home_hours_end = datetime.strptime(config["home_hours"]["end"], "%H:%M").time()
    home_hours_begin = datetime.strptime(config["home_hours"]["begin"], "%H:%M").time()
    work_hours_end = datetime.strptime(config["work_hours"]["end"], "%H:%M").time()
    work_hours_begin = datetime.strptime(config["work_hours"]["begin"], "%H:%M").time()

    home_stay_count = (
        data.filter(
            (
                (
                    (pl.col("time") < home_hours_end)
                    | (pl.col("time") > home_hours_begin)
                )
                & (pl.col("dow") < 6)
            )
            | ((pl.col("dow") >= 6) | (pl.col("day").is_in(config["weekday_holidays"])))
        )
        .group_by([device_id, spatial_id])
        .agg(pl.col("day").count())
        .rename({"day": "count"})
        .sort([device_id, "count"], descending=[False, True])
        .unique(subset=device_id, keep="first")
    )
    work_stay_count = (
        data.filter(
            ((pl.col("time") > work_hours_begin) & (pl.col("time") < work_hours_end))
            & ((pl.col("dow") < 6) | (pl.col("day").is_in(config["weekend_workdays"])))
            & (~pl.col("day").is_in(config["weekday_holidays"]))
        )
        .group_by([device_id, spatial_id])
        .agg(pl.col("day").count())
        .rename({"day": "count"})
        .sort([device_id, "count"], descending=[False, True])
        .unique(subset=device_id, keep="first")
    )
    return home_stay_count.join(
        work_stay_count,
        on=device_id,
        how="full",
        suffix="_work",
        coalesce=True,
    ).rename({spatial_id: f"{spatial_id}_home", "count": "count_home"})


def map_to_settlements(
    data: pl.DataFrame, settlements: gpd.GeoDataFrame
) -> pl.DataFrame:
    gdf = data.to_pandas()
    gdf = gpd.GeoDataFrame(
        gdf,
        geometry=gpd.points_from_xy(gdf["longitude_mean"], gdf["latitude_mean"]),
        crs=4326,
    )
    gdf = gdf.sjoin(settlements).drop(["index_right", "geometry"], axis=1)
    gdf = pl.from_pandas(gdf).with_columns(pl.col("day").dt.date())

    return gdf


def concat_home_tables(path: str, range_start: int = 0, range_end: int = 256) -> None:
    for res in range(7, 11):
        hw = pl.DataFrame()
        for i in range(range_start, range_end):
            temp = pl.read_csv(f"{path}/home_work_{i:02x}_h3_{res}.csv")
            hw = pl.concat([hw, temp])
            del temp
        hw = hw.sort("device_id")
        hw.write_csv(f"{path}/home_work_h3_{res}.csv")
        hw.write_parquet(f"{path}/home_work_h3_{res}.parquet")
        del hw


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import shutil

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="input directory of the detected stops",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="output directory",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="config file (YAML)",
    )
    parser.add_argument(
        "--range_start",
        type=int,
        required=False,
        default=0,
        help="partition range start",
    )
    parser.add_argument(
        "--range_end",
        type=int,
        required=False,
        default=256,
        help="partition range end",
    )
    opts = parser.parse_args()
    Path(opts.output).mkdir(parents=True, exist_ok=True)

    shutil.copy(opts.config, f"{opts.output}/home_detection_config.yaml")

    with open(opts.config, "r") as fp:
        hd_config = yaml.safe_load(fp)

    for i in range(opts.range_start, opts.range_end):
        data = pl.read_parquet(f"{opts.input}/{i:02x}.parquet")
        data = data.with_columns(
            plh3.int_to_str(
                plh3.latlng_to_cell(
                    pl.col("latitude_mean"), pl.col("longitude_mean"), 7
                )
            ).alias("h3_7"),
            plh3.int_to_str(
                plh3.latlng_to_cell(
                    pl.col("latitude_mean"), pl.col("longitude_mean"), 8
                )
            ).alias("h3_8"),
            plh3.int_to_str(
                plh3.latlng_to_cell(
                    pl.col("latitude_mean"), pl.col("longitude_mean"), 9
                )
            ).alias("h3_9"),
            plh3.int_to_str(
                plh3.latlng_to_cell(
                    pl.col("latitude_mean"), pl.col("longitude_mean"), 10
                )
            ).alias("h3_10"),
            pl.col("interval_start").dt.date().alias("day"),
            pl.col("interval_start").dt.time().alias("time"),
            pl.col("interval_start").dt.weekday().alias("dow"),
        )

        hw7 = detect_home_work(
            data, hd_config, spatial_id="h3_7", device_id="device_id"
        )
        hw7.write_csv(f"{opts.output}/home_work_{i:02x}_h3_7.csv")
        hw8 = detect_home_work(
            data, hd_config, spatial_id="h3_8", device_id="device_id"
        )
        hw8.write_csv(f"{opts.output}/home_work_{i:02x}_h3_8.csv")
        hw9 = detect_home_work(
            data, hd_config, spatial_id="h3_9", device_id="device_id"
        )
        hw9.write_csv(f"{opts.output}/home_work_{i:02x}_h3_9.csv")
        hw10 = detect_home_work(
            data, hd_config, spatial_id="h3_10", device_id="device_id"
        )
        hw10.write_csv(f"{opts.output}/home_work_{i:02x}_h3_10.csv")

    concat_home_tables(opts.output, opts.range_start, opts.range_end)
