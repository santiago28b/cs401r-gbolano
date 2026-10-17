"""Run the Lab 3 Track B RAGAS harness against rag/offer.py.

Usage (from the repo root):
    python -m rag.run_eval --label baseline-run1
    python -m rag.run_eval --label baseline-run2
    python -m rag.run_eval --summary          # combine all runs -> docs/lab3-evidence/rag_eval.csv

Each run writes evaluation_results/rag_eval_<label>.csv with per-case scores,
the generated offer, the retrieved chunk IDs and the judge model.
"""
import argparse
import glob
import os

import pandas as pd

import evaluation_harness as eh
from rag.offer import generate_offer

RESULTS_DIR = "evaluation_results"
EVIDENCE_CSV = "docs/lab3-evidence/rag_eval.csv"
METRICS = ["faithfulness", "answer_relevancy", "context_recall"]


def run(label: str, judge: str) -> None:
    chunk_log = []                      # chunk IDs per case, in harness order

    def rag_fn(customer_context, question):
        r = generate_offer(customer_context, question)
        chunk_log.append(r["chunk_ids"])
        return {"answer": r["answer"], "contexts": r["contexts"]}

    evaluator = eh.RAGEvaluator(rag_invoke_fn=rag_fn, bedrock_model_id=judge)
    df = evaluator.run(eh.OFFER_TEST_CASES)

    df.insert(0, "run", label)
    df.insert(1, "customer_id", [tc.customer_id for tc in eh.OFFER_TEST_CASES])
    df["chunk_ids"] = [";".join(ids) for ids in chunk_log]
    df["judge_model"] = judge

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"rag_eval_{label}.csv")
    df.to_csv(out, index=False)

    nan = df[METRICS].isna().sum()
    print(f"\nSaved {out}")
    print(df[["customer_id"] + METRICS].to_string(index=False))
    if nan.any():
        print(f"\nNaN scores (judge call failed, usually throttling; re-run, do not count as 0): {nan[nan > 0].to_dict()}")


def summary() -> None:
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "rag_eval_*.csv")))
    if not files:
        raise SystemExit("No runs found in evaluation_results/")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    os.makedirs(os.path.dirname(EVIDENCE_CSV), exist_ok=True)
    df.to_csv(EVIDENCE_CSV, index=False)

    per_run = df.groupby("run")[METRICS].mean()
    print("Mean per run:\n", per_run.round(3).to_string(), sep="")
    print("\nAcross runs (mean / min / max of the run means):")
    print(per_run.agg(["mean", "min", "max"]).round(3).to_string())
    print(f"\nJudge model(s): {', '.join(df['judge_model'].unique())}")
    print(f"Wrote {EVIDENCE_CSV} ({len(df)} rows from {len(files)} runs)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", help="name for this run, e.g. baseline-run1")
    p.add_argument("--judge", default=eh.DEFAULT_BEDROCK_MODEL_ID,
                   help="Bedrock model RAGAS uses to score answers")
    p.add_argument("--summary", action="store_true",
                   help="combine all runs into docs/lab3-evidence/rag_eval.csv")
    a = p.parse_args()
    if a.summary:
        summary()
    elif a.label:
        run(a.label, a.judge)
    else:
        p.error("give --label NAME or --summary")
