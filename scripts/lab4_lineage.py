"""Lab 4 Task 3: copy lineage onto a registered model package.

For the newest package in northstar-churn-models (or the ARN you pass):
  * finds the training job that produced it (from its ModelDataUrl)
  * reads COMMIT_SHA and the input channel S3 URI off that job
  * reads the evaluation metrics the job uploaded
  * writes them as CustomerMetadataProperties with update-model-package
  * saves describe-model-package to docs/lab4-model-package.json

    python scripts/lab4_lineage.py                 # newest package
    python scripts/lab4_lineage.py <package-arn>   # a specific one
"""

import json
import sys

import boto3

GROUP = "northstar-churn-models"
OUT = "docs/lab4-model-package.json"
METRIC_KEYS = ["auc_roc", "baseline_auc", "precision_top10", "recall_top10",
               "lift_ci_low", "lift_ci_high", "positive_rate_val", "n_val_samples"]

sm = boto3.client("sagemaker")
s3 = boto3.client("s3")

if len(sys.argv) > 1:
    arn = sys.argv[1]
else:
    arn = sm.list_model_packages(ModelPackageGroupName=GROUP, SortBy="CreationTime",
                                 SortOrder="Descending", MaxResults=1
                                 )["ModelPackageSummaryList"][0]["ModelPackageArn"]
pkg = sm.describe_model_package(ModelPackageName=arn)
model_url = pkg["InferenceSpecification"]["Containers"][0]["ModelDataUrl"]
# s3://<bucket>/artifacts/training/<training-job-name>/output/model.tar.gz
job_name = model_url.rstrip("/").split("/")[-3]
job = sm.describe_training_job(TrainingJobName=job_name)

commit = job.get("Environment", {}).get("COMMIT_SHA", "unknown")
data_uri = job["InputDataConfig"][0]["DataSource"]["S3DataSource"]["S3Uri"]

# Data version = newest object under the training prefix at training time.
bucket, _, prefix = data_uri[len("s3://"):].partition("/")
objs = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
data_ts = max(o["LastModified"] for o in objs).isoformat() if objs else "unknown"

metrics_uri = pkg["ModelMetrics"]["ModelQuality"]["Statistics"]["S3Uri"]
mb, _, mk = metrics_uri[len("s3://"):].partition("/")
metrics = json.loads(s3.get_object(Bucket=mb, Key=mk)["Body"].read())

props = {
    "commit_sha": commit,
    "git_repo": "github.com/santiago28b/cs401r-gbolano",
    "training_data_s3_uri": data_uri,
    "training_data_timestamp": data_ts,
    "training_job_name": job_name,
    "training_start_time": job["TrainingStartTime"].isoformat(),
    "training_end_time": job["TrainingEndTime"].isoformat(),
    "billable_seconds": str(job.get("BillableTimeInSeconds", "")),
    "evaluation_metrics_s3_uri": metrics_uri,
    "xgboost_container": "sagemaker-xgboost 1.7-1",
}
props.update({k: str(metrics[k]) for k in METRIC_KEYS if k in metrics})

sm.update_model_package(ModelPackageArn=arn, CustomerMetadataProperties=props)
desc = sm.describe_model_package(ModelPackageName=arn)
desc.pop("ResponseMetadata", None)
with open(OUT, "w") as f:
    json.dump(desc, f, indent=2, default=str)

print(f"Updated {arn}")
for k, v in props.items():
    print(f"  {k:28s} {v}")
print(f"Saved {OUT}")
