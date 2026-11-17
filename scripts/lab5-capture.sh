#!/usr/bin/env bash
# Lab 5 evidence capture, the guide's three windows as one script.
# Run from the repo root inside the cs401r-glue env:
#   bash scripts/lab5-capture.sh 1   # canary live at 9:1 (creates the file)
#   bash scripts/lab5-capture.sh 2   # after rollback-action.sh (appends)
#   bash scripts/lab5-capture.sh 3   # after teardown-lab5.sh (appends)
# Uses `python` (conda env), not `python3` (Homebrew on this Mac, no boto3).
set -uo pipefail
OUT=docs/lab5-deployment-output.txt
EP=northstar-churn-prod
cap () { echo; echo "===== $1 ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ====="; }
traffic () {
python - "$1" <<'PY'
import boto3, collections, sys
rt = boto3.client("sagemaker-runtime", region_name="us-east-1")
body = open("deployment/configs/sample.csv", "rb").read()
c = collections.Counter(
    rt.invoke_endpoint(EndpointName="northstar-churn-prod", ContentType="text/csv",
                       Body=body)["InvokedProductionVariant"]
    for _ in range(int(sys.argv[1])))
print(" / ".join(f"{k} {v}" for k, v in sorted(c.items())), f" (n={sum(c.values())})")
PY
}

case "${1:-}" in
1)
{
echo "Lab 5 deployment evidence - account $(aws sts get-caller-identity --query Account --output text)"
cap "0. Model Registry: versions and approval status"
aws sagemaker list-model-packages --model-package-group-name northstar-churn-models \
  --query 'ModelPackageSummaryList[].[ModelPackageVersion,ModelApprovalStatus,CreationTime]' --output table
cap "1. describe-endpoint: both variants and their weights"
aws sagemaker describe-endpoint --endpoint-name $EP \
  --query '{Status:EndpointStatus,Config:EndpointConfigName,Variants:ProductionVariants[].{Name:VariantName,Weight:CurrentWeight,Instances:CurrentInstanceCount}}'
aws sagemaker describe-endpoint-config \
  --endpoint-config-name "$(aws sagemaker describe-endpoint --endpoint-name $EP --query EndpointConfigName --output text)" \
  --query 'ProductionVariants[].[VariantName,ModelName,InstanceType,InitialVariantWeight]' --output table
cap "2. auto-scaling: register attempt, live targets and policies, quota requests"
aws application-autoscaling register-scalable-target --cli-input-json file://deployment/configs/scalable-target.json
aws application-autoscaling describe-scalable-targets --service-namespace sagemaker
aws application-autoscaling describe-scaling-policies --service-namespace sagemaker
aws service-quotas list-requested-service-quota-change-history --service-code sagemaker --region us-east-1 \
  --query 'RequestedQuotas[].[QuotaName,DesiredValue,Status,Created]' --output table
echo "Applied quota, ml.m5.large for endpoint usage (L-614B09FD): $(aws service-quotas get-service-quota --service-code sagemaker --quota-code L-614B09FD --region us-east-1 --query 'Quota.Value' --output text)"
cap "3. rollback alarm: definition as code, then live state"
cat deployment/configs/rollback-alarm.json
aws cloudwatch describe-alarms --alarm-name-prefix northstar-churn-rollback \
  --query 'MetricAlarms[].[AlarmName,MetricName,ExtendedStatistic,Threshold,EvaluationPeriods,StateValue]' --output table
cap "4. observed traffic split at 9:1"
traffic 200
} 2>&1 | tee "$OUT"
;;
2)
{
cap "5. after rollback: weights, then observed split"
aws sagemaker describe-endpoint --endpoint-name $EP \
  --query 'ProductionVariants[].[VariantName,CurrentWeight]' --output text
traffic 100
} 2>&1 | tee -a "$OUT"
;;
3)
{
cap "6. after teardown: live API"
echo "endpoints: $(aws sagemaker list-endpoints --query 'length(Endpoints)' --output text)"
echo "endpoint configs: $(aws sagemaker list-endpoint-configs --query 'length(EndpointConfigs)' --output text)"
echo "scalable targets: $(aws application-autoscaling describe-scalable-targets --service-namespace sagemaker --query 'length(ScalableTargets)' --output text)"
} 2>&1 | tee -a "$OUT"
;;
*) echo "usage: bash scripts/lab5-capture.sh 1|2|3"; exit 1;;
esac
