# Lab 5 Deployment Plan: NorthStar Churn Model

this is what you do before you start:

Run every command from the repo root (`cs401r-gbolano`) in the `cs401r-glue` conda env, with AWS credentials for account 031310758774, region `us-east-1`. Endpoint name: `northstar-churn-prod`.

## 1. Deployment strategy and rationale

We use a **real-time endpoint with a canary**: one endpoint, two production variants. The champion (registry v10) gets 90% of the traffic and the canary (v11) gets 10%.

NorthStar scores every customer once a week for the retention marketing list. That weekly list goes stale during the week. A customer who was fine on Monday can complain and stop buying by Thursday. When a support rep is on the phone with that customer, they need the score right now, from today's numbers, so they can offer the right promotion. That is the on-demand case, and it needs a real-time endpoint. A canary also needs live traffic to test the new model on a small slice before everyone gets it, and only real-time gives us that. Canary instead of a direct swap means a bad v11 only hits 1 in 10 calls.

## 2. Pre-deployment checklist

1. Endpoint quota is at least 2 for ml.m5.large:
   `aws service-quotas get-service-quota --service-code sagemaker --quota-code L-614B09FD --region us-east-1 --query 'Quota.Value' --output text`
2. Both versions pass the CI gates (P@10 >= 0.50, R@10 >= 0.25, lift CI low > 0).
3. **Model approval.** The ML Lead (model approver) reviews AUC, P@10, R@10 and the lift CI in the registry and approves. In this lab the ML Engineer approved v10 (AUC 0.7804, P@10 0.71, R@10 0.3227, lift CI [0.0373, 0.0756]) and v11 (AUC 0.7810, P@10 0.74, R@10 0.3364, lift CI [0.0392, 0.0762]):
   `aws sagemaker update-model-package --model-package-arn arn:aws:sagemaker:us-east-1:031310758774:model-package/northstar-churn-models/10 --model-approval-status Approved`
4. The MLEngineer role can write `datacapture/*` (IAM statement `S3DataCaptureWrite`), and the lifecycle rule returns `7 1`:
   `aws s3api get-bucket-lifecycle-configuration --bucket northstar-dev-data-031310758774 --query "Rules[?ID=='expire-datacapture'].[Expiration.Days,NoncurrentVersionExpiration.NoncurrentDays]" --output text`
5. `deployment/configs/sample.csv` exists (one header-less row, 11 features in `FEATURE_COLUMNS` order).

Deploy:

```
aws sagemaker create-model --model-name northstar-churn-v10 --primary-container ModelPackageName=arn:aws:sagemaker:us-east-1:031310758774:model-package/northstar-churn-models/10 --execution-role-arn arn:aws:iam::031310758774:role/northstar-dev-MLEngineer
aws sagemaker create-model --model-name northstar-churn-v11 --primary-container ModelPackageName=arn:aws:sagemaker:us-east-1:031310758774:model-package/northstar-churn-models/11 --execution-role-arn arn:aws:iam::031310758774:role/northstar-dev-MLEngineer
aws sagemaker create-endpoint-config --cli-input-json file://deployment/configs/endpoint-config-canary.json
aws sagemaker create-endpoint --endpoint-name northstar-churn-prod --endpoint-config-name northstar-churn-prod-canary-v10-v11
aws sagemaker wait endpoint-in-service --endpoint-name northstar-churn-prod
aws cloudwatch put-metric-alarm --cli-input-json file://deployment/configs/rollback-alarm.json
aws application-autoscaling register-scalable-target --cli-input-json file://deployment/configs/scalable-target.json
aws application-autoscaling put-scaling-policy --cli-input-json file://deployment/configs/scaling-policy.json
bash scripts/lab5-capture.sh 1
```

## 3. Rollback criteria

- **Metric:** `ModelLatency` for the `canary` variant, statistic **p95**, namespace `AWS/SageMaker`.
- **Threshold:** above **200000 microseconds (200 ms)** for **3 consecutive 1-minute periods**. Normal is about 4,100 microseconds. This matches `deployment/configs/rollback-alarm.json` (alarm `northstar-churn-rollback-canary-latency-p95`).
- **Who makes the call:** the on-call engineer runs the rollback as soon as the alarm goes to ALARM, without waiting for approval. The ML Lead is told right after.
- **Action:** `bash deployment/configs/rollback-action.sh` sets the canary weight to 0 (about 90 seconds, no dropped requests). This does not stop the canary instance billing; only deleting the endpoint does.

## 4. Monitoring window

**Production:** 48 hours before promoting the canary to 100%. **This lab:** 60 minutes (6:17 PM to 7:17 PM MST on Nov 16), then rollback, to save endpoint cost.

What we watch: the rollback alarm state, canary p95 latency, 4XX/5XX errors, the observed traffic split, and that `.jsonl` files keep landing in `datacapture/`.

A clean deployment means the alarm stays OK, no 5XX errors, the split is close to 9:1, and data capture works for both variants.

What 60 minutes misses: one hour barely shows anything. In 48 hours we see how customers behave on a weekend versus a weekday, and at peak versus slow times. We also get enough calls to trust the numbers: in our hour the canary only answered 17 of 200 calls in the split test. Rare customer types and problems that build up slowly (latency creeping up, memory, errors over time) need hours or days to show up. In a real rollout we would also compare the canary's score distribution to the champion's on the same customers.

## 5. Stakeholder notifications

| Stage | Who | What they get |
|---|---|---|
| Deployment start | ML Engineer, ML Lead, On-call engineer | New model going live at 10%, versions and the rollback alarm name |
| Promotion to 100% | ML Engineer, Retention Marketing Lead, Customer Support Lead | New model is live for everyone; scores may shift a bit |
| Rollback | Everyone above | On-call and ML Lead: what broke and the alarm details. Marketing and Support: we are back on the old model, scores are back to normal |

## 6. Post-deployment review

Held **one week after promotion**, so we have a full week of traffic to judge fairly. Attendees: ML Engineer, ML Lead, On-call engineer and Retention Marketing Lead (they can say if the scores actually helped). We review the numbers and any bugs. The output is a short **written review** (what happened, the numbers, what to change next time), saved with the deployment evidence for everyone to read.

## 7. Resource cleanup

After the window closes, delete in this order: scaling policy, scalable target, rollback alarm, endpoint, endpoint config, models. The kit script does all of it:

```
bash scripts/teardown-lab5.sh
bash scripts/lab5-capture.sh 3
```

Cleanup is verified against the live API, not the console: `docs/lab5-teardown-output.txt` must show OK on all 6 lines, and section 6 of `docs/lab5-deployment-output.txt` must show 0 endpoints, 0 endpoint configs and 0 scalable targets.
