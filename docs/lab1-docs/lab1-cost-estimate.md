# Lab 1 — Monthly Cost Estimate

Steady-state monthly cost for the NorthStar dev platform (us-east-1),
estimated with the AWS Pricing Calculator.

| Component | Monthly Estimate | Key Assumptions | One Optimization |
|---|---|---|---|
| SageMaker Studio | $4.40 | 4 hrs/day at $0.05/hr on ml.t3.medium | |
| S3 storage | $0.35 | 15 GB at $0.023/GB | |
| Internet Gateway | $0.05 | $0.01/GB data transfer, 5 GB/month | |
| DynamoDB (state lock) | $0.00 | On-demand, near-zero reads/writes | |
| S3 state bucket | $0.00 | Minimal storage, versioned | |
| **Total** | **$4.80** | | |

## Assumptions

- TODO: one line per estimate above, stating where the number comes from.
for sagemaker studio: number of data scienties: 1, isnatnces per data scitntis: 1 hours per day: 4 days per month:22

for s3: in features prefix. engineered features for 2.1M customers, refreshed weekly for scoring. If each customer's feature row is roughly 500 bytes, that's 2.1M × 500 B rougly 1 GB per weekly snapshot. 12 weeks of history and lead us to around 15 GB.

## Quantified Optimization

- TODO: one specific change, with the estimated monthly saving.
if we left running 24/7 is 730 × $0.05 = $36.50; we have is $4.40; shutting the space down when idle saves $32.10/month
