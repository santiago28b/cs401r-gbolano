# Lab 1 — Monthly Cost Estimate

Steady-state monthly cost for the NorthStar dev platform (us-east-1),
estimated with the AWS Pricing Calculator.

| Component | Monthly Estimate | Key Assumptions | One Optimization |
|---|---|---|---|
| SageMaker Studio | $X.XX | X hrs/day at $Y/hr on ml.t3.medium | |
| S3 storage | $X.XX | X GB at $0.023/GB | |
| Internet Gateway | $X.XX | $0.01/GB data transfer, X GB/month | |
| DynamoDB (state lock) | $X.XX | On-demand, near-zero reads/writes | |
| S3 state bucket | $X.XX | Minimal storage, versioned | |
| **Total** | **$X.XX** | | |

## Assumptions

- TODO: one line per estimate above, stating where the number comes from.

## Quantified Optimization

- TODO: one specific change, with the estimated monthly saving.
