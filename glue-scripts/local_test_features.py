"""
Local test runner for glue-scripts/feature_engineer.py  (not deployed, not graded)

Builds processed/customers/ locally by running YOUR transform.py functions on
northstar-raw-sample.csv, then runs your five feature functions on it and
prints the same checks the Glue job asserts and verify-lab2.sh runs.
No AWS calls; Feature Store ingest is skipped.

Run from the repo root, inside the cs401r-glue conda env:

    python glue-scripts/local_test_features.py

Expected numbers when everything is right:
    observation window rows   130,189
    outcome window rows        27,438
    customers with features     9,999
    churn_label rate            ~22.0%
    tiers  Bronze 3,529 / Silver 3,862 / Gold 1,664 / Platinum 944
"""

import os
import sys
import types

# Both scripts import awsglue, which only exists on Glue. Stub it.
for _name in ["awsglue", "awsglue.context", "awsglue.job", "awsglue.utils"]:
    sys.modules[_name] = types.ModuleType(_name)
sys.modules["awsglue.context"].GlueContext = object
sys.modules["awsglue.job"].Job = object
sys.modules["awsglue.utils"].getResolvedOptions = lambda *a, **k: {}

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import transform  # noqa: E402  (your Task 2 code)
import feature_engineer as fe  # noqa: E402  (your Task 3 code)
from local_test_transform import load_like_glue, check  # noqa: E402

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

FEATURE_COLS = [
    "days_since_last_purchase", "customer_tenure_days",
    "purchase_frequency_30d", "purchase_frequency_90d",
    "purchase_frequency_180d", "avg_order_value", "total_spend_90d",
    "total_lifetime_value", "avg_basket_size_6m",
    "category_diversity_score", "online_to_store_ratio",
]
ALL_COLS = FEATURE_COLS + ["loyalty_tier", "churn_risk_score", "churn_label"]


def main():
    spark = (SparkSession.builder
             .master("local[*]")
             .appName("local-test-features")
             .config("spark.sql.shuffle.partitions", "8")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    # processed/customers/, built with your transform functions
    df = load_like_glue(spark)
    df = transform.deduplicate(transform.impute_nulls(transform.cast_types(df))).cache()
    print(f"\nprocessed rows (input):    {df.count():,}")

    history, holdout = fe.split_windows(df)
    history, holdout = history.cache(), holdout.cache()
    print(f"observation window rows:   {history.count():,}")
    print(f"outcome window rows:       {holdout.count():,}")

    feats = fe.compute_rfm_features(history)
    feats = fe.assign_loyalty_tier(feats)
    feats = fe.compute_churn_proxy(feats)
    feats = fe.attach_churn_label(feats, holdout).cache()

    n = feats.count()
    distinct = feats.select("customer_id").distinct().count()
    print(f"customers with features:   {n:,}")

    rate = feats.agg(F.avg("churn_label")).collect()[0][0]
    print(f"churn_label rate:          {rate:.1%}" if rate is not None else "churn_label rate: n/a")

    print("\ntier counts:")
    feats.groupBy("loyalty_tier").count().orderBy("count").show()

    print("checks (same as the Glue job and verify-lab2.sh):")
    missing = [c for c in ALL_COLS if c not in feats.columns]
    check("all 14 feature columns present", not missing, f"missing: {missing}" if missing else "")
    if missing:
        spark.stop()
        return

    check("one row per customer", n == distinct, f"{n:,} rows, {distinct:,} customers")

    nulls = {c: feats.filter(F.col(c).isNull()).count() for c in ALL_COLS}
    bad = {c: v for c, v in nulls.items() if v}
    check("no null feature values", not bad, f"{bad}" if bad else "")

    types_now = dict(feats.dtypes)
    not_double = {c: types_now[c] for c in FEATURE_COLS + ["churn_risk_score"]
                  if types_now[c] != "double"}
    check("features are double (Feature Store Fractional)", not not_double,
          f"{not_double}" if not_double else "")
    check("churn_label is an integer type (Feature Store Integral)",
          types_now["churn_label"] in ("int", "bigint"), types_now["churn_label"])

    lo, hi = feats.agg(F.min("churn_risk_score"), F.max("churn_risk_score")).collect()[0]
    check("churn_risk_score in [0, 1]", lo is not None and lo >= 0 and hi <= 1, f"min {lo}, max {hi}")
    nd = feats.select("churn_risk_score").distinct().count()
    check("churn score non-degenerate (scaled within bands)", nd > 3, f"{nd} distinct values")

    check("churn_label rate plausible (15-30%)", rate is not None and 0.15 <= rate <= 0.30,
          f"{rate:.1%}" if rate is not None else "n/a")

    tiers = {r[0] for r in feats.select("loyalty_tier").distinct().collect()}
    check("all 4 loyalty tiers present", tiers == {"Bronze", "Silver", "Gold", "Platinum"},
          ", ".join(sorted(map(str, tiers))))

    hi_div = feats.agg(F.max("category_diversity_score")).collect()[0][0]
    check("category_diversity_score <= 1.0 ('unknown' excluded)", hi_div <= 1.0, f"max {hi_div}")

    churn_min = feats.filter("churn_label = 1").agg(F.min("days_since_last_purchase")).collect()[0][0]
    active_max = feats.filter("churn_label = 0").agg(F.max("days_since_last_purchase")).collect()[0][0]
    check("label not trivially separable by recency (no leak)",
          churn_min is not None and active_max is not None and churn_min < active_max,
          f"churner min recency {churn_min} vs active max {active_max}")

    neg = feats.filter(F.col("days_since_last_purchase") < 0).count()
    check("no negative recency (nothing after T leaked in)", neg == 0, f"{neg} rows")

    print("\nsample rows:")
    feats.orderBy("customer_id").show(3, truncate=False, vertical=True)
    spark.stop()


if __name__ == "__main__":
    main()
