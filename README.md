# cs401r-gbolano: NorthStar Retail AI Platform

CS 401R "Engineering the AI Enterprise", Fall 2026. One repo for all seven labs. Each lab builds on the one before it.

## Repo layout

```
infrastructure/
  modules/        vpc, storage, iam, sagemaker (Lab 1), glue, feature_store (Lab 2)
  environments/
    dev/          real AWS, state in S3 with a DynamoDB lock
    local/        LocalStack (no NAT, no lifecycle rules, no SageMaker)
glue-scripts/     transform.py, feature_engineer.py (+ local test runners)
scripts/          verify-labN.sh, teardown-lab2.sh, check-secrets.sh
docs/             graded evidence for each lab
```

## Lab 1: Platform foundation

VPC with a public subnet, Internet Gateway and route table; one S3 data bucket with four prefixes (`raw/`, `processed/`, `features/`, `artifacts/`); the MLEngineer IAM role; and a SageMaker Studio domain. Everything is in Terraform.

## Lab 2: Data and feature engineering

### What changed in the existing modules

| Module | Change |
|---|---|
| `vpc` | Private subnet `10.0.1.0/24`, Elastic IP, NAT Gateway in the public subnet, private route table (`0.0.0.0/0` to the NAT). `enable_nat_gateway` turns the NAT off for LocalStack. The security group got a self-referencing ingress rule, which Glue needs. |
| `storage` | Five lifecycle rules (`expire-raw-data`, `expire-raw-versions`, `expire-processed-versions`, `expire-feature-versions`, `expire-datacapture`). `enable_lifecycle_rules` turns them off for LocalStack. |
| `iam` | New `DataEngineer` role (Glue, Lambda and SageMaker can assume it; writes `raw/`, `processed/`, `features/`; reads only `artifacts/glue/`) and `ModelMonitor` role (read-only on `artifacts/`, writes CloudWatch metrics only). |
| `sagemaker` | Domain moved to the private subnet with `app_network_access_type = "VpcOnly"`, so Studio traffic goes out through the NAT. |

### New modules

- **`glue`**: catalog database `northstar_dev`, crawler `northstar-dev-raw-crawler` over `raw/customers/`, a NETWORK connection that runs Glue workers in the private subnet, and two ETL jobs (`northstar-dev-transform` and `northstar-dev-feature-engineer`). Terraform also uploads both scripts to `artifacts/glue/`.
- **`feature_store`**: SageMaker Feature Group `northstar-dev-customer-features` with 16 feature definitions, online store on, offline store in `features/offline-store/`.

### Data flow

```
raw/customers/ (CSV)
  -> crawler -> catalog table northstar_dev.customers
  -> transform job -> processed/customers/ (Parquet, one row per transaction)
  -> feature engineer job -> features/customers/ (Parquet, one row per customer)
                          -> Feature Store (PutRecord) -> features/offline-store/
```

Features are computed only from purchases on or before T = 2026-04-01. `churn_label` comes only from the 90 days after T. See `docs/lab2-data-lineage.png` and `docs/lab2-data-contract.md`.

### How to run the pipeline end to end

All commands from the repo root.

```bash
# 1. Infrastructure
terraform -chdir=infrastructure/environments/dev init
terraform -chdir=infrastructure/environments/dev apply

# 2. Load the raw data
BUCKET=$(terraform -chdir=infrastructure/environments/dev output -raw s3_bucket_name)
aws s3 cp northstar-raw-sample.csv s3://$BUCKET/raw/customers/northstar-raw-sample.csv

# 3. Crawl raw/ (wait for state READY)
aws glue start-crawler --name northstar-dev-raw-crawler
aws glue get-crawler --name northstar-dev-raw-crawler --query 'Crawler.State'

# 4. Transform: raw -> processed (wait for SUCCEEDED)
aws glue start-job-run --job-name northstar-dev-transform
aws glue get-job-runs --job-name northstar-dev-transform --query 'JobRuns[0].JobRunState'

# 5. Features: processed -> features/ + Feature Store (wait for SUCCEEDED)
aws glue start-job-run --job-name northstar-dev-feature-engineer
aws glue get-job-runs --job-name northstar-dev-feature-engineer --query 'JobRuns[0].JobRunState'

# 6. Verify while the stack is up
bash scripts/verify-lab2.sh 2>&1 | tee docs/lab2-verify-output.txt
```

### Testing the Glue scripts locally

Glue runs take minutes to start, so both scripts can be tested on a laptop first (needs Java 17, `pyspark==3.3.0`, `boto3`):

```bash
python glue-scripts/local_test_transform.py   # expect 157,627 rows, 9,999 customers
python glue-scripts/local_test_features.py    # expect 9,999 customers, ~22% churn
```

LocalStack check for the network, storage and IAM modules:

```bash
make local-validate LOCAL_OUT=docs/lab2-localstack-output.txt
```

### Teardown

`terraform destroy` alone leaves resources behind in this lab (Glue ENIs, the Studio EFS volume, S3 versions and more). Use:

```bash
bash scripts/teardown-lab2.sh 2>&1 | tee docs/lab2-destroy-output.txt
```

The NAT Gateway bills about $1/day while it exists, so tear down after submitting.

## Lab 3: Model development

Two systems on top of the Lab 2 Feature Store: a churn model (Track A) and a RAG offer generator (Track B). Design reasoning is in `docs/lab3-model-design.md`; the churn evaluation is in `docs/lab3-evaluation-report.md`.

### Prerequisites

- Lab 2 stack up and the feature job run, so the Feature Store offline store has data.
- MLflow **App** (not a Tracking Server) created once: `aws sagemaker create-mlflow-app --name northstar-mlflow --artifact-store-uri s3://<bucket>/artifacts/mlflow/ --role-arn <MLEngineer role>` (bucket and role from `terraform output`).
- Python env with `xgboost scikit-learn 'sagemaker<3' mlflow sagemaker-mlflow matplotlib faiss-cpu ragas datasets "langchain-community<0.4" langchain-aws`.
- Bedrock access verified: `docs/bedrock-access-verification.txt`.

### Train the churn model (Track A)

Trains locally on data pulled from the Feature Store offline store through Athena, logs the run to the MLflow App and registers it as `PendingManualApproval` in `northstar-churn-models`. All hyperparameters come from arguments.

```bash
export MLFLOW_ARN=<your MLflow App ARN>      # printed by create-mlflow-app
BUCKET=$(terraform -chdir=infrastructure/environments/dev output -raw s3_bucket_name)

python churn_training_skeleton.py --artifacts-bucket $BUCKET \
  --model-dir /tmp/l3-model --output-data-dir docs/lab3-evidence \
  --mlflow-arn $MLFLOW_ARN --run-name final-depth6-autoweight \
  --max-depth 6 --eta 0.1 --num-round 200 2>&1 | tee docs/lab3-evidence/train-final.log
```

Outputs:

| File | What |
|---|---|
| `docs/lab3-evidence/train-final.log` | console log of the graded run, with the Athena QueryExecutionId |
| `docs/lab3-evidence/evaluation_metrics.json` | AUC, precision/recall @ top 10%, recency baseline AUC, lift and 95% CI |
| `docs/lab3-evidence/slice-evaluation.csv` | per loyalty tier: n, positives, AUC, recall, too-small flag |
| `docs/lab3-evidence/confusion-matrix.png`, `feature-importance.png` | plots from the registered model |
| `s3://<bucket>/artifacts/models/churn/<run-name>/model.tar.gz` | model artifact referenced by the registry version |

### Build and evaluate the RAG offer generator (Track B)

```bash
python rag/ingest.py                              # chunk + embed the policy docs -> rag/index/
python -m rag.run_eval --label baseline-run1      # RAGAS harness, 4 test cases (RAG_RETRIEVAL=single for the old single-query retrieval)
python -m rag.run_eval --summary                  # combine runs -> docs/lab3-evidence/rag_eval.csv
jupyter nbconvert --to notebook --execute --inplace notebooks/lab3-demo.ipynb
```

| Path | What |
|---|---|
| `rag/ingest.py` | section chunking, Titan V2 embeddings, FAISS index |
| `rag/offer.py` | retrieval (single or multi-query) + Claude Haiku 4.5 offer generation |
| `rag/run_eval.py` | runs `evaluation_harness.py` (Track B) and saves per-run CSVs to `evaluation_results/` |
| `docs/lab3-evidence/rag_eval.csv` | all RAGAS runs, with offers, chunk IDs and judge model |
| `docs/lab3-evidence/track-b-examples.md` | 5 correct examples and 2 failure cases with fixes |
| `notebooks/lab3-demo.ipynb` | end-to-end demo, committed with outputs |

### Evidence and teardown

```bash
PATH="$CONDA_PREFIX/bin:$PATH" bash scripts/collect-lab3-evidence.sh --track B   # before teardown
bash scripts/teardown-lab3.sh                                                     # writes docs/lab3-teardown-output.txt
```

The MLflow App is kept on purpose (no cost, used again in Labs 4 and 6).
