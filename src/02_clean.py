import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from common import read_day, daterange


def clean_os_version(x) -> float:
    result = x
    if "." in x:
        result = x.strip().split(".")[0]
    if x.strip() in ["ANDROID", "IOS", "Other", "null", ""]:
        result = np.nan
    return float(result)


with open("../config.yaml", "r") as fp:
    config = yaml.safe_load(fp)

with open("../output/id_lookup/id_lookup.json", "r") as fp:
    lookup = json.load(fp)

with open("../data/os_version.yaml", "r") as fp:
    os_versions = yaml.safe_load(fp)
os_versions["ios"] = {k: v.strftime("%Y-%m-%d") for k, v in os_versions["ios"].items()}
os_versions["android"] = {
    k: v.strftime("%Y-%m-%d") if isinstance(v, date) else v
    for k, v in os_versions["android"].items()
}

to_drop = [
    # "aid_type",
    "horizontal_accuracy",
    "altitude",
    "altitude_accuracy",
    "ip",
    # "user_agent",
    "model",
    "carrier",
    "OS",
    "OS_version",
    "manufacturer",
    "location_method",
]

OUTPUT = f"{config['dirs']['output']}/partitioned"
SET_TIMEZONE = True

for i in daterange(date(2025, 7, 1), date(2025, 12, 31)):
    print(i.strftime("%Y-%m-%d"))
    data = read_day(i, config["dirs"]["pickwell"])
    data = data.with_columns(pl.from_epoch(pl.col("timestamp"), time_unit="s"))

    # Clean OS version
    if "OS_version" not in to_drop:
        data = data.with_columns(
            pl.col("OS_version")
            .fill_null("")
            .map_elements(clean_os_version, return_dtype=float)
        )

    # Drop insignificant columns
    data = data.drop(to_drop)

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
        pl.col("device_aid_hashed").str.slice(0, 2).alias("partition")
    )
    # Replace device IDs
    data = data.with_columns(pl.col("device_aid_hashed").replace_strict(lookup))
    data = data.rename({"device_aid_hashed": "device_id"})

    for p in data.partition_by("partition"):
        path = f"{OUTPUT}/{p['partition'][0]}"
        Path(path).mkdir(exist_ok=True, parents=True)
        p_ = p.sort(["device_id", "timestamp"]).drop("partition")
        p_.write_parquet(f"{path}/pings_{i.strftime('%Y_%m_%d')}.parquet")

        del p_
    del data
