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
