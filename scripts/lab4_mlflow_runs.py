"""Lab 4 Task 3: export MLflow App runs (mlflow.search_runs) as evidence.

    python scripts/lab4_mlflow_runs.py | tee docs/lab4-mlflow-runs.txt

Needs MLFLOW_APP_ARN in the environment (or pass the ARN as the first arg),
plus mlflow and sagemaker-mlflow installed (the cs401r-glue conda env has both).
These are MLflow App runs, NOT the Experiments a SageMaker Pipeline auto-creates.
"""

import os
import sys

import mlflow
import pandas as pd

arn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MLFLOW_APP_ARN")
if not arn:
    sys.exit("Set MLFLOW_APP_ARN or pass the MLflow App ARN.")
EXPERIMENT = "northstar-churn"

mlflow.set_tracking_uri(arn)
runs = mlflow.search_runs(experiment_names=[EXPERIMENT],
                          order_by=["attributes.start_time ASC"])

want = ["tags.mlflow.runName", "start_time",
        "params.max_depth", "params.eta", "params.num_round", "params.min_child_weight",
        "params.subsample", "params.colsample_bytree", "params.scale_pos_weight",
        "params.xgboost_version",
        "metrics.auc_roc", "metrics.baseline_auc", "metrics.lift_ci_low",
        "metrics.lift_ci_high", "metrics.precision_top10", "metrics.recall_top10"]
cols = [c for c in want if c in runs.columns]
table = runs[cols].copy()
table.columns = [c.split(".", 1)[-1] for c in cols]

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
print(f"mlflow.search_runs  tracking_uri={arn}")
print(f"experiment={EXPERIMENT}  runs={len(runs)}")
print()
print(table.to_string(index=False))
hp = [c for c in table.columns if c in ("max_depth", "eta", "num_round", "min_child_weight",
                                        "subsample", "colsample_bytree", "scale_pos_weight")]
print()
print(f"distinct hyperparameter combinations: {len(table[hp].drop_duplicates())}")
