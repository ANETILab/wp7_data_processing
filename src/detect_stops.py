import infostop
import numpy as np
import polars as pl
from pyproj import Transformer


def filter_pings(df: pl.DataFrame, min_pings: int) -> pl.DataFrame:
    """Keep only devices with at least min_pings pings."""
    valid_devices = (
        df.group_by("device_id")
        .len()
        .filter(pl.col("len") >= min_pings)["device_id"]
        .to_list()
    )
    return df.filter(pl.col("device_id").is_in(valid_devices))


def cluster_pings(
    filtered: pl.DataFrame, model: infostop.models.Infostop
) -> pl.DataFrame:
    """run infostop per device -- data is expected to be already sorted, no re-sort needed in loop
    catch devices with no stop events (all pings labelled -1)
    """
    results = []
    for device_id, group in filtered.group_by("device_id"):
        coords = group[["latitude", "longitude", "epoch"]].to_numpy()
        try:
            labels = model.fit_predict(coords)
        except Exception:
            labels = np.full(len(coords), -1)
        group_ = group.with_columns(place_label=labels)

        results.append(group_)

    clustered = pl.concat(results)
    clustered = clustered.sort(["device_id", "timestamp"]).drop("epoch")
    return clustered


def assign_stop_ids(clustered: pl.DataFrame) -> pl.DataFrame:
    """assign stop_id: a sequential integer per device, incrementing each time a new stop begins.
    stop_id is independent of place_label -- the same place visited twice gets two different stop_ids.
    pings with place_label == -1 (movement) get stop_id == -1.
    """
    result = clustered.with_columns(
        pl.when(pl.col("place_label") >= 0)
        .then(
            (
                (pl.col("place_label") >= 0)
                & (pl.col("place_label").shift(1).over("device_id").fill_null(-1) != pl.col("place_label"))
            )
            .cast(pl.Int32)
            .cum_sum()
            .over("device_id")
        )
        .otherwise(-1)
        .alias("stop_id")
    )
    return result


def create_stop_table(
    clustered: pl.DataFrame, transformer: Transformer
) -> pl.DataFrame:
    # to calculate the standard deviation of the pings in a cluster (stop) in meters, project the coordinates
    projected = transformer.transform(clustered["latitude"], clustered["longitude"])
    clustered = clustered.with_columns(
        latitude_proj=projected[0], longitude_proj=projected[1]
    )

    # aggregate pings to stops; place_label is constant within a (device_id, stop_id) after assign_stop_ids
    stops = (
        clustered.filter(pl.col.stop_id >= 0)
        .group_by(["device_id", "stop_id"])
        .agg(
            interval_start=pl.col.timestamp.min(),
            interval_stop=pl.col.timestamp.max(),
            interval_lenght=pl.col.timestamp.max() - pl.col.timestamp.min(),
            latitude_mean=pl.col.latitude.mean(),
            longitude_mean=pl.col.longitude.mean(),
            latitude_std=pl.col.latitude_proj.std().round(),
            longitude_std=pl.col.longitude_proj.std().round(),
            number_of_pings=pl.col.longitude.count(),
            place_label=pl.col.place_label.first(),
        )
        .sort(["device_id", "stop_id"])
    )
    return stops


if __name__ == "__main__":
    import yaml

    with open("../config.yaml") as fp:
        config = yaml.safe_load(fp)
    with open("05_detect_stops_config.yaml") as fp:
        stop_detections_config = yaml.safe_load(fp)

    # configure infostop
    params = stop_detections_config["infostop"]

    model = infostop.Infostop(
        r1=params["r1"],
        r2=params["r2"],
        min_staying_time=params["min_staying_time"],
        max_time_between=params["max_time_between"],
        min_size=params["min_size"],
        distance_metric=params["distance_metric"],
    )

    # set up transformer for reprojection
    transformer = Transformer.from_crs(4326, config["crs"])

    for i in range(256):
        data = pl.read_parquet(
            f"{config['dirs']['output']}/partitioned/{i:02x}/pings.parquet"
        )
        filtered = filter_pings(
            data, min_pings=stop_detections_config["filtering"]["min_pings_per_day"]
        )
        del data
        filtered = filtered.with_columns(
            pl.col("timestamp").dt.epoch(time_unit="s").alias("epoch")
        )
        clustered = cluster_pings(filtered, model)
        del filtered
        clustered = assign_stop_ids(clustered)

        stops = create_stop_table(clustered, transformer)
        stops.write_parquet(f"{config['dirs']['output']}/stops/{i:02x}.parquet")

        del stops
        del clustered
