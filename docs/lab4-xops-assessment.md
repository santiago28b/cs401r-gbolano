# Lab 4: XOps, CI/CD and MLOps configuration

## 1. CI/CD pipeline: the five phases and where they run (Task 2)

Implementation: AWS CodePipeline + CodeBuild + a SageMaker Pipeline, defined in `pipeline.yaml`, `buildspec.yml` and `models/churn/pipeline_definition.py`.

Why CodePipeline: everything else in NorthStar already lives in AWS (data bucket, Glue, SageMaker, Model Registry, CloudWatch, SNS). CodeBuild runs with an IAM role, so no AWS access keys are stored in GitHub, which matters because this repo is public. It also talks to SageMaker, CloudWatch and SNS directly, so the alarm and the approval topic need no extra glue code. GitHub Actions would work, but it would need keys or an OIDC role set up just to reach the same services.

| Phase | CodePipeline stage | Where it runs | What enforces it |
|---|---|---|---|
| 1. Source | Source | CodeConnections connection `northstar-github` on `main` of `santiago28b/cs401r-gbolano` | Every push to `main` starts a run (`DetectChanges: true`) |
| 2. Test | Build | `buildspec.yml` **pre_build**: `pytest tests/` (data, feature and any other test file; only the two model-gate files are left for later because they need a trained model) | Any failing test exits pre_build non-zero, so CodeBuild never starts the build phase. Nothing is trained or registered. |
| 3. Build | Build | `buildspec.yml` **build**: upserts and starts the SageMaker Pipeline. Its `TrainChurnModel` step packages `models/churn/` and runs `train_sagemaker.py` -> `churn_model.train()` on a managed spot instance | Training fails if `evaluate_model()` raises (precision@10% < 0.50, recall@10% < 0.25, or the lift CI includes 0) |
| 4. Evaluate | Build | `buildspec.yml` **build**, after training: `pytest tests/test_model.py tests/test_fairness.py` against the real artifact and `evaluation_metrics.json` (gates, model loading, monotonicity, champion regression vs the newest Approved package, fairness flag) | A failing gate fails the build; `post_build` sets the just-registered package to **Rejected** |
| 5. Register | Build (SageMaker step `RegisterChurnModel`) then ManualApproval | `RegisterModel` with `PendingManualApproval`; a human then approves in the Model Registry and the CodePipeline `ManualApproval` stage (SNS topic `northstar-model-approvals`) | The pipeline never approves its own model |

Five phases run in three CodePipeline stages (Source, Build, ManualApproval). Stages are where artifacts hand off or a human steps in. The four automated phases share one CodeBuild project, so they are not split into more stages.

Failure notification: CloudWatch alarm `northstar-ci-build-failure` on `AWS/CodeBuild FailedBuilds` (emitted even when pre_build fails, unlike a metric published from post_build) -> SNS `northstar-model-approvals` -> email. Proof: `docs/lab4-failure-demo.txt`.

Evidence: `docs/lab4-pipeline-runs.txt`, `docs/lab4-build-green.log`, `docs/lab4-failure-demo.txt`, `docs/lab4-build-failed.log`.

## 2. MLOps configuration (Task 3)

### Champion-challenger criterion

A challenger replaces the champion only if **both** are true:

1. It passes every CI gate (precision@10% >= 0.50, recall@10% >= 0.25, lift CI over the recency baseline excludes 0, not more than 0.02 AUC below the champion).
2. **Its test AUC is at least the champion's AUC + 0.01.**

Yes or no, nothing in between. Why 0.01: the same code on the same data already moves AUC by a few thousandths depending on the XGBoost version and split (0.7854 in the SageMaker container vs 0.7822 on my machine for the same commit). A gain smaller than 0.01 could just be that noise, and swapping models has a cost (new approval, new deploy). So a model that only ties the champion stays in the registry but does not get approved.

Note the CI regression test (`tests/test_model.py::TestChampionRegression`) is a different, looser rule on purpose: it only blocks a model that is **worse** by more than 0.02. Passing CI means "safe to consider"; +0.01 is what earns the swap.

### Retraining triggers

**Scheduled:** retrain **every week** (Monday 06:00 UTC). An **Amazon EventBridge Scheduler** rule calls `StartPipelineExecution` on `northstar-churn-pipeline` with the latest feature set. Weekly matches how often NorthStar scores churn, so each week's scores come from a model trained on last week's data. The Glue feature job runs first on the same schedule, so the 48-hour freshness test passes.

**Performance-based:** two signals, both automatic.

- **Early warning: feature drift.** SageMaker Model Monitor compares this week's inputs against the training baseline. If the PSI of `days_since_last_purchase` (our strongest signal) goes **above 0.2**, it publishes a CloudWatch metric, a **CloudWatch alarm** fires, and an **EventBridge** rule starts the SageMaker Pipeline. This needs no labels, so it fires within a week.
- **Confirmation: real performance.** We only know who actually churned 90 days later (the outcome window). When a window closes, a scheduled job scores those customers and publishes the AUC to CloudWatch. If it drops **below 0.74**, a CloudWatch alarm fires and EventBridge starts the pipeline. 0.74 is about 0.04 under what the model does today (0.785) and still above the recency-only baseline (0.72), so it catches real decay before the model is no better than the free rule.

Both go through the same CI gates, and a human still approves the result.

### Experiment tracking

`docs/lab4-mlflow-runs.txt`: `mlflow.search_runs` against the SageMaker MLflow App, experiment `northstar-churn`, 7 runs with 3 hyperparameter combinations (max_depth 6 vs 3, scale_pos_weight 3.545 vs 1.0), each with params and metrics logged. The Experiments the SageMaker Pipeline creates by itself are not used as evidence.

### Model lineage

`docs/lab4-model-package.json`: `describe-model-package` for v7. `CustomerMetadataProperties` holds `commit_sha`, `training_data_s3_uri` + `training_data_timestamp`, the training job name, and the evaluation metrics. Written by `scripts/lab4_lineage.py`, which reads them off the training job and the metrics file it uploaded.

## 3. XOps maturity assessment (Task 4)

## DataOps Maturity

**Current level: 2**

Evidence:
- The raw -> processed -> features path is code, not clicks: `glue-scripts/transform.py`, `glue-scripts/feature_engineer.py`, deployed by Terraform in `infrastructure/modules/glue/`.
- The feature logic is now unit tested: `data/feature_engineering.py` (a pandas copy of the Glue logic that matches its output exactly) and `tests/test_features.py` (24 tests, incl. zero-purchase and single-purchase customers).
- Data is checked on every push: `tests/test_data.py` checks schema, grain, leakage (recomputes features from pre-cutoff rows only and compares), ranges and 48-hour freshness. A missing dataset fails, it does not skip.
- `docs/lab4-failure-demo.txt` shows a failing test stopping the run before training.

Gap to Level 3: the Glue jobs still start by hand (`aws glue start-job-run`). That's why the freshness test exists at all. There is also no data quality check *inside* the job and no tracking of which data version fed which run, beyond the S3 timestamp I copy onto the model package.

Top priority investment: an **EventBridge schedule that runs crawler -> transform -> feature job weekly**, with **AWS Glue Data Quality** rules (null rate, row count, churn rate 15-30%) that stop the job before it writes a bad feature set.

## MLOps Maturity

**Current level: 2**

Evidence:
- A push to `main` runs the whole loop with no clicks: `pipeline.yaml` (CodePipeline + CodeBuild + alarm + SNS), `buildspec.yml`, `models/churn/pipeline_definition.py` (spot training + `RegisterModel`). See `docs/lab4-pipeline-runs.txt`.
- Training is my Lab 3 code behind a contract: `models/churn/churn_model.py`.
- The model is gated three ways: inside training (`evaluate_model()` raises), in CI (`tests/test_model.py` incl. champion regression, `docs/lab4-build-green.log`), and by a human approval.
- Lineage is on the package: commit SHA, data URI + timestamp, metrics (`docs/lab4-model-package.json`). Experiments are in MLflow (`docs/lab4-mlflow-runs.txt`).
- A failed build alerts by email (`northstar-ci-build-failure` -> SNS, proven in `docs/lab4-failure-demo.txt`).

Gap to Level 3: nothing watches the model after it is approved. There is no deployed endpoint yet (Lab 5) and **no drift or performance monitoring** (Lab 6), so the retraining triggers above are designed but not built. Approval is also a manual step with no deploy behind it.

Top priority investment: **SageMaker Model Monitor** on the Lab 5 endpoint, with the PSI > 0.2 CloudWatch alarm wired through **EventBridge** to `StartPipelineExecution`. That turns retraining from "someone notices" into an automatic loop.
