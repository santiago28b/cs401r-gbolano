"""
Local test runner for glue-scripts/transform.py  (not deployed, not graded)

Runs your three transform functions on northstar-raw-sample.csv with a local
Spark session, then prints the same checks the Glue job asserts. Use it to
catch mistakes in seconds instead of waiting 2-5 minutes per Glue run.

Run from the repo root, inside the cs401r-glue conda env:

    python glue-scripts/local_test_transform.py

Expected numbers when all three functions are right:
    raw rows             163,255
    after cast_types     159,990   (3,265 dropped for null customer_id)
    after deduplicate    157,627   (2,363 duplicate transactions removed)
    distinct customers     9,999
"""

import os
import sys
import types

# transform.py imports awsglue, which only exists on Glue. Stub it so the
# import succeeds locally. Only your three functions are exercised here.
for _name in ["awsglue", "awsglue.context", "awsglue.job", "awsglue.utils"]:
    sys.modules[_name] = types.ModuleType(_name)
sys.modules["awsglue.context"].GlueContext = object
sys.modules["awsglue.job"].Job = object
sys.modules["awsglue.utils"].getResolvedOptions = lambda *a, **k: {}

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import transform  # noqa: E402  (your code)

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

CSV_PATH = os.path.join(REPO, "northstar-raw-sample.csv")


def load_like_glue(spark):
    """Read the CSV the way the crawler registered it in the catalog:
    order_value as double, num_items as bigint, everything else string.
    Empty fields stay as "" in string columns, so cast_types must turn
    them into real nulls itself (as it must on Glue)."""
    df = (spark.read
          .option("header", "true")
          .option("nullValue", "__never_matches__")
          .csv(CSV_PATH))
    return (df
            .withColumn("order_value", F.col("order_value").cast("double"))
            .withColumn("num_items", F.col("num_items").cast("bigint")))


def check(label, passed, detail=""):
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    return passed


def main():
    spark = (SparkSession.builder
             .master("local[*]")
             .appName("local-test-transform")
             .config("spark.sql.shuffle.partitions", "8")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    df = load_like_glue(spark)
    raw = df.count()
    print(f"\nraw rows:            {raw:,}")

    df = transform.cast_types(df)
    after_cast = df.count()
    print(f"after cast_types:    {after_cast:,}  ({raw - after_cast:,} dropped)")

    df = transform.impute_nulls(df)
    after_impute = df.count()
    print(f"after impute_nulls:  {after_impute:,}")

    df = transform.deduplicate(df).cache()
    final = df.count()
    print(f"after deduplicate:   {final:,}  ({after_impute - final:,} removed)")

    customers = df.select("customer_id").distinct().count()
    print(f"distinct customers:  {customers:,}\n")

    print("schema:")
    df.printSchema()

    print("checks (same as the Glue job and verify-lab2.sh):")
    types_now = dict(df.dtypes)
    expected = {"transaction_id": "string", "customer_id": "string",
                "purchase_date": "date", "order_value": "double",
                "num_items": "int", "payment_method": "string",
                "channel": "string", "store_id": "string",
                "product_category": "string"}
    wrong = {c: types_now.get(c) for c, t in expected.items()
             if types_now.get(c) != t}
    check("column types match SCHEMA", not wrong, f"wrong: {wrong}" if wrong else "")

    n = df.filter(F.col("customer_id").isNull()).count()
    check("no null customer_id", n == 0, f"{n} nulls")

    n = df.filter(F.col("purchase_date").isNull()).count()
    check("no null purchase_date", n == 0, f"{n} nulls")

    dups = final - df.select("transaction_id").distinct().count()
    check("no duplicate transaction_id", dups == 0, f"{dups} duplicates")

    check("transaction-level grain kept (many rows per customer)",
          final > customers * 5, f"{final:,} rows / {customers:,} customers")

    nulls = {c: df.filter(F.col(c).isNull()).count()
             for c in transform.NUMERIC_COLS + transform.STRING_COLS}
    left = {c: v for c, v in nulls.items() if v}
    check("no nulls left in imputed columns", not left, f"{left}" if left else "")

    blanks = {c: df.filter(F.col(c) == "").count() for c in transform.STRING_COLS}
    left = {c: v for c, v in blanks.items() if v}
    check("no empty strings left in string columns", not left, f"{left}" if left else "")

    ws = df.filter(F.col("customer_id") != F.trim(F.col("customer_id"))).count()
    check("customer_id has no stray whitespace", ws == 0, f"{ws} rows")

    print("\nsample rows:")
    df.orderBy("transaction_id").show(5, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
