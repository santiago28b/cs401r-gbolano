"""Your Lab 3 churn model, packaged for the Lab 4 pipeline.

YOU WRITE THIS FILE. The pipeline's training job runs train_sagemaker.py
(beside this file; do not edit it), which imports this module and calls
train(). Everything the job needs from you goes through the three names below.

Contract (train_sagemaker.py checks it in the first seconds of the job):

    FEATURE_COLUMNS   list[str]   model input columns, in order
    LABEL             str         "churn_label"
    train(df, seed=42) -> (xgboost.Booster, dict)

`df` is the full labeled feature table: every column of your Lab 2 output,
including `loyalty_tier` for slice evaluation. It is already loaded. Do not
query Athena or the Feature Store from here; the training container stages
the data for you and has no business making service calls for its input.

The metrics dict must include the four numbers the CI gate in
tests/test_model.py reads. Your Lab 3 evaluate_model() already returns them:

    precision_top10, recall_top10      gated at 0.50 / 0.25
    lift_ci_low, lift_ci_high          bootstrap 95% CI on AUC lift over the
                                       recency-only baseline; lift_ci_low > 0

Include anything else you reported in Lab 3 (auc_roc, baseline_auc,
positive_rate_val, slice results). It is all written to evaluation_metrics.json
and attached to the registered model.

What runs in the container: the SageMaker XGBoost 1.7-1 image ships pandas,
numpy, scikit-learn, xgboost and boto3. It does NOT ship mlflow or sagemaker,
so do not import them at the top of this file. MLflow tracking stays in your
Lab 3 script.

Only this directory (models/churn/) is uploaded to the training job, so the
code must live here. `import churn_training_skeleton` will fail inside the
container even though it works on your laptop. Copy the functions you need.

Test it locally before pushing:

    python models/churn/train_sagemaker.py \
        --train-channel <dir containing your features CSV or Parquet> \
        --model-dir /tmp/model --output-data-dir /tmp/out
"""

# Keeps Lab 3 annotations like `-> tuple[np.ndarray, np.ndarray]` from being
# evaluated, whatever Python the training container runs.
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

# Must match the columns your Lab 3 model was trained on, in the same order.
# (Same list as churn_training_skeleton.py. churn_risk_score is excluded on
# purpose: it is the recency heuristic.)
FEATURE_COLUMNS = [
    "days_since_last_purchase",
    "customer_tenure_days",
    "purchase_frequency_30d",
    "purchase_frequency_90d",
    "purchase_frequency_180d",
    "avg_order_value",
    "total_spend_90d",
    "total_lifetime_value",
    "avg_basket_size_6m",
    "category_diversity_score",
    "online_to_store_ratio",
]

LABEL = "churn_label"
SLICE_COLUMN = "loyalty_tier"
BASELINE_FEATURE = "days_since_last_purchase"
MIN_SLICE_POSITIVES = 30

# Lab 3 graded run "final-depth6-autoweight": skeleton defaults, auto scale_pos_weight.
HYPERPARAMS = {
    "max_depth": 6,
    "eta": 0.1,
    "num_round": 200,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
}

EVAL_THRESHOLDS = {"precision_top10": 0.50, "recall_top10": 0.25}
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42


# ── Copied from churn_training_skeleton.py (Lab 3) ─────────────────────────────

def preprocess_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Same as Lab 3: sentinel -1 for any missing feature value."""
    X = df[FEATURE_COLUMNS].astype(float).fillna(-1).to_numpy()
    y = df[LABEL].astype(int).to_numpy()
    print(f"  Positive class rate: {y.mean():.1%} | Feature matrix: {X.shape}")
    return X, y


def train_model(X_train, y_train, X_val, y_val, seed: int = 42) -> tuple[xgb.Booster, float]:
    """Lab 3 train_model(). scale_pos_weight computed from the training split."""
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
    spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],   # keep auc LAST: early stopping uses the last one
        "max_depth": HYPERPARAMS["max_depth"],
        "eta": HYPERPARAMS["eta"],
        "min_child_weight": HYPERPARAMS["min_child_weight"],
        "subsample": HYPERPARAMS["subsample"],
        "colsample_bytree": HYPERPARAMS["colsample_bytree"],
        "scale_pos_weight": spw,
        # Churn risk may only rise as days_since_last_purchase rises (business
        # rule; tests/test_model.py checks it). +1 on recency, free elsewhere.
        "monotone_constraints": "(" + ",".join("1" if c == BASELINE_FEATURE else "0" for c in FEATURE_COLUMNS) + ")",
        "seed": seed,
        "verbosity": 1,
    }
    model = xgb.train(params=params, dtrain=dtrain,
                      num_boost_round=HYPERPARAMS["num_round"],
                      evals=[(dtrain, "train"), (dval, "validation")],
                      early_stopping_rounds=20, verbose_eval=25)
    return model, spw


def train_recency_baseline(X_train, y_train, X_val) -> np.ndarray:
    """Lab 3 baseline: XGBoost on days_since_last_purchase ALONE, same rows."""
    i = FEATURE_COLUMNS.index(BASELINE_FEATURE)
    dtr = xgb.DMatrix(X_train[:, [i]], label=y_train, feature_names=[BASELINE_FEATURE])
    dva = xgb.DMatrix(X_val[:, [i]], feature_names=[BASELINE_FEATURE])
    spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    params = {"objective": "binary:logistic", "eval_metric": "auc",
              "max_depth": 4, "eta": 0.1, "subsample": 0.9,
              "colsample_bytree": 0.9, "scale_pos_weight": spw, "seed": 42}
    return xgb.train(params, dtr, num_boost_round=200).predict(dva)


def bootstrap_lift_ci(y_true, proba, baseline_proba, n: int = BOOTSTRAP_N,
                      seed: int = BOOTSTRAP_SEED, alpha: float = 0.05) -> tuple[float, float]:
    """Paired bootstrap CI on (model AUC - baseline AUC), same as Lab 3."""
    rng = np.random.default_rng(seed)
    y_true = np.asarray(y_true)
    idx = np.arange(len(y_true))
    diffs = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        ys = y_true[s]
        if len(np.unique(ys)) < 2:
            continue
        diffs.append(roc_auc_score(ys, proba[s]) - roc_auc_score(ys, baseline_proba[s]))
    if len(diffs) < n // 2:
        raise ValueError("Too few usable bootstrap replicates to form a confidence interval.")
    d = np.sort(diffs)
    return float(np.quantile(d, alpha / 2)), float(np.quantile(d, 1 - alpha / 2))


def evaluate_model(model: xgb.Booster, X_val, y_val, baseline_proba) -> dict:
    """Lab 3 evaluate_model(). Raises ValueError on a failed gate, so the
    training step fails and the model is never registered."""
    proba = model.predict(xgb.DMatrix(X_val, feature_names=FEATURE_COLUMNS))
    auc_roc = roc_auc_score(y_val, proba)
    top10 = proba >= np.percentile(proba, 90)
    precision_top10 = y_val[top10].mean() if top10.sum() > 0 else 0.0
    recall_top10 = y_val[top10].sum() / y_val.sum() if y_val.sum() > 0 else 0.0
    baseline_auc = roc_auc_score(y_val, baseline_proba)
    lo, hi = bootstrap_lift_ci(y_val, proba, baseline_proba)

    metrics = {
        "auc_roc": round(float(auc_roc), 4),
        "precision_top10": round(float(precision_top10), 4),
        "recall_top10": round(float(recall_top10), 4),
        "auc_vs_baseline": round(float(auc_roc - baseline_auc), 4),
        "baseline_auc": round(float(baseline_auc), 4),
        "baseline_auc_roc": round(float(baseline_auc), 4),
        "lift_ci_low": round(float(lo), 4),
        "lift_ci_high": round(float(hi), 4),
        "positive_rate_val": round(float(y_val.mean()), 4),
        "n_val_samples": int(len(y_val)),
        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print("\n── Evaluation Results ──")
    failures = []
    for name, threshold in EVAL_THRESHOLDS.items():
        ok = metrics[name] >= threshold
        print(f"  {name:20s}: {metrics[name]:.4f} (threshold {threshold:.2f}) {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"{name}={metrics[name]:.4f} < {threshold}")
    print(f"  {'auc_lift 95% CI':20s}: [{lo:.4f}, {hi:.4f}] (must exclude 0) {'PASS' if lo > 0 else 'FAIL'}")
    if lo <= 0:
        failures.append(f"auc_lift 95% CI [{lo:.4f}, {hi:.4f}] includes zero")
    if failures:
        raise ValueError(f"Model failed evaluation thresholds: {'; '.join(failures)}. "
                         f"Do not promote to Model Registry.")
    return metrics


def evaluate_slices(model: xgb.Booster, X_val, y_val, tiers) -> dict:
    """Lab 3 evaluate_slices(): per-tier recall at the GLOBAL top-10% cutoff.
    Plain Python types only, so the result can go into evaluation_metrics.json."""
    proba = model.predict(xgb.DMatrix(X_val, feature_names=FEATURE_COLUMNS))
    cutoff = np.percentile(proba, 90)
    flagged = proba >= cutoff
    aggregate_recall = float(y_val[flagged].sum() / y_val.sum()) if y_val.sum() > 0 else 0.0
    tiers = np.asarray(tiers, dtype=object)

    results = {}
    for tier in sorted(set(tiers)):
        mask = tiers == tier
        y_s, p_s = y_val[mask], proba[mask]
        positives = int(y_s.sum())
        recall = float(y_s[p_s >= cutoff].sum() / positives) if positives > 0 else 0.0
        auc = float(roc_auc_score(y_s, p_s)) if len(np.unique(y_s)) == 2 else None
        results[str(tier)] = {
            "n": int(mask.sum()),
            "positives": positives,
            "auc": None if auc is None else round(auc, 4),
            "recall_top10": round(recall, 4),
            "too_small": positives < MIN_SLICE_POSITIVES,
            "below_aggregate_by_10pp": bool(positives >= MIN_SLICE_POSITIVES
                                            and recall < aggregate_recall - 0.10),
        }
    return {"aggregate_recall_top10": round(aggregate_recall, 4), "tiers": results}


# ── The Lab 4 contract ─────────────────────────────────────────────────────────

def train(df: pd.DataFrame, seed: int = 42):
    """Train the churn model on `df` and return (booster, metrics).

    Same steps and split as the Lab 3 graded run: dropna on the label,
    70/30 stratified split with the tier carried through the same call,
    XGBoost, recency-only baseline, evaluate_model (raises on a failed gate),
    per-tier slices.
    """
    df = df.dropna(subset=[LABEL]).reset_index(drop=True)
    X, y = preprocess_features(df)
    tiers = df[SLICE_COLUMN].to_numpy(dtype=object)

    X_train, X_val, y_train, y_val, _tier_train, tier_val = train_test_split(
        X, y, tiers, test_size=0.30, random_state=seed, stratify=y)
    print(f"Train: {len(X_train):,} | Validation: {len(X_val):,}")

    model, spw = train_model(X_train, y_train, X_val, y_val, seed=seed)
    baseline_proba = train_recency_baseline(X_train, y_train, X_val)
    metrics = evaluate_model(model, X_val, y_val, baseline_proba)

    slices = evaluate_slices(model, X_val, y_val, tier_val)
    metrics["slice_results"] = slices["tiers"]
    metrics["aggregate_recall_top10"] = slices["aggregate_recall_top10"]
    metrics["scale_pos_weight"] = round(spw, 4)
    metrics["best_iteration"] = int(getattr(model, "best_iteration", -1))
    metrics["n_train_samples"] = int(len(y_train))
    metrics["hyperparameters"] = dict(HYPERPARAMS)

    print("Slices:", {t: (r["recall_top10"], r["positives"]) for t, r in slices["tiers"].items()})
    return model, metrics
