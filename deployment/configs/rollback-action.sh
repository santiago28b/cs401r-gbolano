#!/usr/bin/env bash
# Rollback: send 0% of traffic to the canary, 100% to the champion.
# Run from the repo root: bash deployment/configs/rollback-action.sh
# Takes ~90 s. The endpoint keeps serving while it reports Updating.
# This does NOT stop the canary instance billing; only deleting the endpoint does.
set -euo pipefail
EP=northstar-churn-prod
aws sagemaker update-endpoint-weights-and-capacities \
  --endpoint-name "$EP" \
  --desired-weights-and-capacities \
    VariantName=champion,DesiredWeight=1 \
    VariantName=canary,DesiredWeight=0
echo "Rollback requested. Waiting for InService..."
aws sagemaker wait endpoint-in-service --endpoint-name "$EP"
aws sagemaker describe-endpoint --endpoint-name "$EP" \
  --query 'ProductionVariants[].[VariantName,CurrentWeight]' --output text
