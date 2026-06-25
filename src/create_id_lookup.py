import polars as pl
from common import read_day, daterange


def collect_ids(
    days: list, raw_pings_path: str, id_column: str, id_type_column: str
) -> list[str]:
    ids = []
    for i in days:
        temp = read_day(i, raw_pings_path).with_columns(
            pl.concat_str(
                [pl.col("device_aid_hashed"), pl.col("device_aid_type")], separator="."
            ).alias("id_with_type")
        )
        dids = temp.unique(subset=["id_with_type"], keep="first")[
            "id_with_type"
        ].to_list()
        ids += dids
    return ids


def create_lookup(ids: list[str]) -> dict[str, int]:
    df = pl.DataFrame([ids], schema=["id_with_type"]).with_row_index(
        "device_id", offset=1
    )
    return dict(zip(df["id_with_type"], df["device_id"]))


def create_partitions(lookup: dict[str, int]) -> dict:
    return {v: k[:2] for k, v in lookup.items()}


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
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

    OUTPUT = f"{config['dirs']['output']}/{config['city']}/id_lookup"
    Path(OUTPUT).mkdir(parents=True, exist_ok=True)

    days = []
    for i in config["days"]:
        days += list(daterange(i["start"], i["end"]))

    # runs 30 minutes for Budapest data
    ids = collect_ids(
        days,
        config["dirs"]["raw_source"],
        id_column=config["id_column"],
        id_type_column=config["id_type_column"],
    )

    lookup = create_lookup(ids)

    with open(f"{OUTPUT}/id_lookup.json", "w") as fp:
        json.dump(lookup, fp, indent=1)

    partition = create_partitions(lookup)

    with open(f"{OUTPUT}/partition.json", "w") as fp:
        json.dump(partition, fp, indent=1)
