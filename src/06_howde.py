"""
HoWDe Home/Work Detection — Parallel Run

Processes all .parquet files in paths.input_dir (configured in 06_howde_config.yaml)
concurrently via ThreadPoolExecutor.  One output file is written per input file to
paths.output_dir with processing.output_suffix appended to the stem
(e.g. 00.parquet → 00_howde.parquet).  Already-completed files are skipped so
interrupted runs can be resumed.

Usage:
    python 06_howde.py [config.yaml]   # defaults to 06_howde_config.yaml
"""

import os
import sys
import glob
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Config  (must load before pyspark so driver_memory reaches the JVM)
# ---------------------------------------------------------------------------
config_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "06_howde_config.yaml")

with open(config_path) as fp:
    config = yaml.safe_load(fp)

cfg_paths = config["paths"]
cfg_howde = config["howde"]
cfg_spark = config["spark"]
cfg_proc  = config["processing"]

# spark.driver.memory must be set before the JVM starts — SparkSession.config is too late.
# PYSPARK_SUBMIT_ARGS is read by pyspark when it launches the JVM process.
os.environ["PYSPARK_SUBMIT_ARGS"] = (
    f"--driver-memory {cfg_spark['driver_memory']} "
    "--conf spark.driver.extraJavaOptions='-XX:ReservedCodeCacheSize=512m' "
    "pyspark-shell"
)

import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from howde import HoWDe_labelling

# ---------------------------------------------------------------------------
# Spark session
# ---------------------------------------------------------------------------
# spark.scheduler.mode=FAIR is required so concurrent queries submitted by the
# ThreadPoolExecutor workers truly interleave rather than queue up (FIFO default).
# shuffle.partitions is scaled to CPU count for local runs — remove for cluster.
spark = (
    SparkSession.builder
    .appName("HoWDeParallel")
    .config("spark.scheduler.mode", cfg_spark["scheduler_mode"])
    .config("spark.sql.shuffle.partitions", str(os.cpu_count() * cfg_spark["shuffle_partitions_per_cpu"]))  # local only — remove for cluster
    .config("spark.sql.execution.arrow.pyspark.enabled", str(cfg_spark["arrow_enabled"]).lower())
    .config("spark.sql.session.timeZone", cfg_spark["timezone"])
    .getOrCreate()
)

# ---------------------------------------------------------------------------
# Per-file processing function
# ---------------------------------------------------------------------------
def process_file(parquet_path):
    stem     = os.path.splitext(os.path.basename(parquet_path))[0]
    out_name = stem + cfg_proc["output_suffix"] + ".parquet"
    out_path = os.path.join(cfg_paths["output_dir"], out_name)

    if os.path.exists(out_path):
        return {"file": out_name, "status": "skipped"}

    t0 = time.perf_counter()
    try:
        raw = spark.read.parquet(parquet_path)

        # UTC offset per stop (accounts for DST: CET = +1h, CEST = +2h)
        utc_str     = F.date_format(F.col("interval_start"), "yyyy-MM-dd HH:mm:ss")
        local_str   = F.date_format(
            F.from_utc_timestamp(F.col("interval_start"), cfg_proc["local_timezone"]),
            "yyyy-MM-dd HH:mm:ss"
        )
        offset_secs = F.unix_timestamp(local_str) - F.unix_timestamp(utc_str)

        input_data = (
            raw
            .withColumnRenamed("device_id", "useruuid")
            .withColumnRenamed("stop_id", "loc")
            .withColumn("start", F.unix_timestamp(F.col("interval_start")))
            .withColumn("end",   F.unix_timestamp(F.col("interval_stop")))
            .withColumn("tz_hour_start",   (offset_secs / 3600).cast("long"))
            .withColumn("tz_minute_start", ((offset_secs % 3600) / 60).cast("long"))
            .withColumn("country", F.lit(cfg_proc["country"]))
            .select("useruuid", "loc", "start", "end", "tz_hour_start", "tz_minute_start", "country")
        )
        input_data = input_data.repartitionByRange(os.cpu_count(), "useruuid")

        labeled = HoWDe_labelling(input_data, **cfg_howde, verbose=False)
        pdf = labeled.toPandas()
        pdf.to_parquet(out_path, index=False)

        return {"file": out_name, "status": "ok", "rows": len(pdf), "elapsed": time.perf_counter() - t0}

    except Exception as exc:
        return {"file": out_name, "status": "error", "error": str(exc), "elapsed": time.perf_counter() - t0}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    input_files = sorted(glob.glob(os.path.join(cfg_paths["input_dir"], "*.parquet")))
    os.makedirs(cfg_paths["output_dir"], exist_ok=True)

    print(f"Input files found : {len(input_files)}")
    print(f"Output directory  : {cfg_paths['output_dir']}")
    print(f"Max parallel files: {cfg_proc['max_parallel_files']}")
    print()

    t_total = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=cfg_proc["max_parallel_files"]) as executor:
        futures = {executor.submit(process_file, p): p for p in input_files}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            if res["status"] == "ok":
                print(f"[{i:>3}/{len(input_files)}] OK      {res['file']}  {res['rows']:>8} rows  {res['elapsed']:.1f}s")
            elif res["status"] == "skipped":
                print(f"[{i:>3}/{len(input_files)}] SKIPPED {res['file']}")
            else:
                print(f"[{i:>3}/{len(input_files)}] ERROR   {res['file']}  {res['error']}")

    print(f"\nTotal elapsed: {time.perf_counter() - t_total:.1f}s")

    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors  = [r for r in results if r["status"] == "error"]

    print(f"\nCompleted : {len(ok)}")
    print(f"Skipped   : {len(skipped)}")
    print(f"Errors    : {len(errors)}")
    if ok:
        print(f"Total rows: {sum(r['rows'] for r in ok):,}")
    if errors:
        print("\nFailed files:")
        for r in errors:
            print(f"  {r['file']}: {r['error']}")
