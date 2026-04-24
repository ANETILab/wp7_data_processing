import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl


def clean_os_version(x: str) -> float:
    result = x
    if "." in x:
        result = x.strip().split(".")[0]
    if x.strip() in ["ANDROID", "IOS", "Other", "null", ""]:
        result = np.nan
    return float(result)


def merge_partitions(partition_path: str) -> list[tuple[int, date]]:
    """
    Merges the daily partitions, and gives back a list of partition/day tuples if the combination didn't exist.
    """
    missing = []
    for i in range(256):
        data = pl.DataFrame()
        for d in days:
            if not Path(
                f"{partition_path}/{i:02x}/pings_{d.strftime('%Y_%m_%d')}.parquet"
            ).is_file():
                missing.append((i, d))
                continue
            dd = pl.read_parquet(
                f"{partition_path}/{i:02x}/pings_{d.strftime('%Y_%m_%d')}.parquet"
            )
            data = pl.concat([data, dd])
            del dd
        data.sort(["device_id", "timestamp"]).write_parquet(
            f"{partition_path}/{i:02x}/pings.parquet"
        )
        del data
    return missing


if __name__ == "__main__":
    import structlog
    import argparse
    import yaml
    from common import read_day, daterange

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

    OUTPUT = f"{config['dirs']['output']}/{config['city']}"
    SET_TIMEZONE = True

    days = []
    for i in config["days"]:
        days += list(daterange(i["start"], i["end"]))

    with open(f"{OUTPUT}/id_lookup/id_lookup.json", "r") as fp:
        lookup = json.load(fp)

    with open("../data/os_version.yaml", "r") as fp:
        os_versions = yaml.safe_load(fp)
    os_versions["ios"] = {
        k: v.strftime("%Y-%m-%d") for k, v in os_versions["ios"].items()
    }
    os_versions["android"] = {
        k: v.strftime("%Y-%m-%d") if isinstance(v, date) else v
        for k, v in os_versions["android"].items()
    }

    for i in days:
        log.info(i.strftime("%Y-%m-%d"))
        data = read_day(i, config["dirs"]["raw_source"])
        data = data.with_columns(pl.from_epoch(pl.col("timestamp"), time_unit="s"))

        # Clean OS version
        if "OS_version" not in config["columns_to_drop"]:
            data = data.with_columns(
                pl.col("OS_version")
                .fill_null("")
                .map_elements(clean_os_version, return_dtype=float)
            )

        # Drop insignificant columns
        data = data.drop(config["columns_to_drop"])

        # Set timezone
        dt_format = "%Y-%m-%d %H:%M:%S"
        if SET_TIMEZONE:
            data = data.with_columns(
                timestamp=pl.col("timestamp").dt.convert_time_zone(
                    time_zone="Europe/Budapest"
                ),
            )
            dt_format = "%Y-%m-%d %H:%M:%S %z"

        data = data.with_columns(
            pl.col(config["id_column"]).str.slice(0, 2).alias("partition")
        )
        # Replace device IDs
        data = data.with_columns(pl.col(config["id_column"]).replace_strict(lookup))
        data = data.rename({config["id_column"]: "device_id"})

        for p in data.partition_by("partition"):
            path = f"{OUTPUT}/partitioned/{p['partition'][0]}"
            Path(path).mkdir(exist_ok=True, parents=True)
            p_ = p.sort(["device_id", "timestamp"]).drop("partition")
            p_.write_parquet(f"{path}/pings_{i.strftime('%Y_%m_%d')}.parquet")

            del p_
        del data

    # merge partitions (runs 45m for Budapest)
    missing = merge_partitions(f"{OUTPUT}/partitioned")

    Path(f"{OUTPUT}/debug/").mkdir(exist_ok=True, parents=True)
    with open(f"{OUTPUT}/debug/03_merge_partitions_missing_log.json", "w") as fp:
        json.dump([(i[0], i[1].strftime("%Y-%m-%d")) for i in missing], fp, indent=1)
