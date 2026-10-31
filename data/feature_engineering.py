"""Lab 2 feature logic in plain pandas, so it can be unit tested.

This is a port of glue-scripts/feature_engineer.py (compute_rfm_features,
assign_loyalty_tier). Same rules as the Glue job:

  * only purchases on or before T (the cutoff) are used
  * windows count back from T by whole days: "in the last 30 days" means
    0 <= (T - purchase_date).days <= 30
  * avg_basket_size_6m = items per order over the last 180 days (not dollars),
    0 when there were no orders in that window
  * category_diversity_score = distinct categories / 8, NOT counting 'unknown'
  * online_to_store_ratio = share of orders where channel == 'online'

Null strategy: a customer on the roster with no purchases before T gets
days_since_last_purchase = customer_tenure_days = NO_HISTORY_SENTINEL (999)
and 0 for every count, sum, average and ratio. Nothing is left as NaN.
"""

from __future__ import annotations

import pandas as pd

FEATURE_CUTOFF = pd.Timestamp("2026-04-01")
N_CATEGORIES = 8.0
NO_HISTORY_SENTINEL = 999

TIER_BRONZE_MAX = 500.0
TIER_SILVER_MAX = 2000.0
TIER_GOLD_MAX = 5000.0

RECENCY_COLS = ["days_since_last_purchase", "customer_tenure_days"]
FREQUENCY_COLS = ["purchase_frequency_30d", "purchase_frequency_90d",
                  "purchase_frequency_180d"]
MONETARY_COLS = ["avg_order_value", "total_spend_90d", "total_lifetime_value",
                 "avg_basket_size_6m"]
BEHAVIORAL_COLS = ["category_diversity_score", "online_to_store_ratio"]
FEATURE_COLUMNS = RECENCY_COLS + FREQUENCY_COLS + MONETARY_COLS + BEHAVIORAL_COLS


def _history(transactions: pd.DataFrame, snapshot_date) -> pd.DataFrame:
    """Rows on or before T, with days_before_T added (0 = bought on T)."""
    T = pd.Timestamp(snapshot_date).normalize()
    df = transactions.copy()
    df["purchase_date"] = pd.to_datetime(df["purchase_date"]).dt.normalize()
    df = df[df["purchase_date"] <= T]
    df["days_before_T"] = (T - df["purchase_date"]).dt.days
    return df


def _with_roster(features: pd.DataFrame, customer_ids, fill: dict) -> pd.DataFrame:
    """Left-join onto a roster so customers with no purchases still get a row."""
    if customer_ids is None:
        return features
    roster = pd.DataFrame({"customer_id": pd.Series(customer_ids["customer_id"]
                                                    if isinstance(customer_ids, pd.DataFrame)
                                                    else customer_ids).unique()})
    out = roster.merge(features, on="customer_id", how="left")
    return out.fillna(fill)


def compute_recency_features(transactions: pd.DataFrame, snapshot_date,
                             customer_ids=None) -> pd.DataFrame:
    """days_since_last_purchase and customer_tenure_days, measured to T."""
    h = _history(transactions, snapshot_date)
    g = h.groupby("customer_id")["days_before_T"]
    out = pd.DataFrame({
        "days_since_last_purchase": g.min(),   # last purchase = fewest days before T
        "customer_tenure_days": g.max(),       # first purchase = most days before T
    }).reset_index().astype({c: float for c in RECENCY_COLS})
    return _with_roster(out, customer_ids, {c: float(NO_HISTORY_SENTINEL) for c in RECENCY_COLS})


def compute_frequency_features(transactions: pd.DataFrame, snapshot_date,
                               customer_ids=None) -> pd.DataFrame:
    """Order counts in the 30 / 90 / 180 days up to and including T."""
    h = _history(transactions, snapshot_date)
    d = h["days_before_T"]
    h = h.assign(**{f"purchase_frequency_{n}d": (d <= n).astype(float) for n in (30, 90, 180)})
    out = h.groupby("customer_id")[FREQUENCY_COLS].sum().reset_index()
    return _with_roster(out, customer_ids, {c: 0.0 for c in FREQUENCY_COLS})


def compute_monetary_features(transactions: pd.DataFrame, snapshot_date,
                              customer_ids=None) -> pd.DataFrame:
    """avg_order_value, total_spend_90d, total_lifetime_value, avg_basket_size_6m."""
    h = _history(transactions, snapshot_date)
    d = h["days_before_T"]
    h = h.assign(spend_90d=h["order_value"].where(d <= 90, 0.0),
                 items_180d=h["num_items"].where(d <= 180, 0),
                 orders_180d=(d <= 180).astype(float))
    g = h.groupby("customer_id").agg(
        avg_order_value=("order_value", "mean"),
        total_spend_90d=("spend_90d", "sum"),
        total_lifetime_value=("order_value", "sum"),
        items_180d=("items_180d", "sum"),
        orders_180d=("orders_180d", "sum"),
    )
    # guarded denominator, same as Glue: no orders in 180 days -> 0, not a divide by zero
    g["avg_basket_size_6m"] = g["items_180d"] / g["orders_180d"].clip(lower=1)
    out = g[MONETARY_COLS].astype(float).reset_index()
    return _with_roster(out, customer_ids, {c: 0.0 for c in MONETARY_COLS})


def compute_behavioral_features(transactions: pd.DataFrame, snapshot_date=None,
                                customer_ids=None) -> pd.DataFrame:
    """category_diversity_score and online_to_store_ratio.

    Pass snapshot_date to restrict to purchases on or before T (what the Glue
    job does). Without it, every row given is used.
    """
    h = _history(transactions, snapshot_date) if snapshot_date is not None else transactions
    known_cat = h["product_category"].where(h["product_category"] != "unknown")
    h = h.assign(known_cat=known_cat, is_online=(h["channel"] == "online").astype(float))
    g = h.groupby("customer_id").agg(n_categories=("known_cat", "nunique"),
                                     online_to_store_ratio=("is_online", "mean"))
    g["category_diversity_score"] = g["n_categories"] / N_CATEGORIES
    out = g[BEHAVIORAL_COLS].astype(float).reset_index()
    return _with_roster(out, customer_ids, {c: 0.0 for c in BEHAVIORAL_COLS})


def assign_loyalty_tier(features: pd.DataFrame) -> pd.DataFrame:
    """Bronze < 500 <= Silver <= 2000 < Gold <= 5000 < Platinum (same as Glue)."""
    ltv = features["total_lifetime_value"]
    tier = pd.Series("Platinum", index=features.index)
    tier[ltv <= TIER_GOLD_MAX] = "Gold"
    tier[ltv <= TIER_SILVER_MAX] = "Silver"
    tier[ltv < TIER_BRONZE_MAX] = "Bronze"
    return features.assign(loyalty_tier=tier)


def build_churn_feature_set(customers: pd.DataFrame, transactions: pd.DataFrame,
                            snapshot_date=FEATURE_CUTOFF) -> pd.DataFrame:
    """One row per customer on the roster, all 11 model features, no NaNs.

    `customers` must have customer_id; any other columns it carries
    (loyalty_tier, churn_label) are kept as they are.
    """
    roster = customers[["customer_id"]].drop_duplicates()
    out = roster
    for part in (compute_recency_features(transactions, snapshot_date, roster),
                 compute_frequency_features(transactions, snapshot_date, roster),
                 compute_monetary_features(transactions, snapshot_date, roster),
                 compute_behavioral_features(transactions, snapshot_date, roster)):
        out = out.merge(part, on="customer_id", how="left")
    extra = [c for c in customers.columns if c != "customer_id" and c not in out.columns]
    if extra:
        out = out.merge(customers[["customer_id"] + extra].drop_duplicates("customer_id"),
                        on="customer_id", how="left")
    return out
