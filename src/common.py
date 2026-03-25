import polars as pl
from datetime import date, timedelta
from pathlib import Path


def daterange(start_date: date, end_date: date):
    days = (end_date - start_date).days
    for n in range(days + 1):
        yield start_date + timedelta(n)


def read_day(d: date, path: str) -> pl.DataFrame:
    path = Path(f"{path}/{d.strftime('%Y/%m/%d')}")
    df = pl.DataFrame()
    for i in sorted(path.glob("*.csv.gz")):
        part = pl.read_csv(
            i,
            separator="\t",
            quote_char=None,
            schema_overrides={"altitude_accuracy": pl.Float64, "OS_version": pl.String},
        )
        df = pl.concat([df, part])
    return df


def determine_descriptives(d: date, path: str) -> dict[str, int]:
    df = read_day(d, path)
    return {
        "number_of_records": len(df),
        "number_of_unique_devices": len(df.unique(subset=["device_aid_hashed"])),
    }
