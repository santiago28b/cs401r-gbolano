#!/usr/bin/env bash
# Lab 4 prerequisites 1, 2 and 6, plus the SNS email subscription.
# Safe to re-run: every step checks before it creates.
#
#   bash scripts/lab4-deploy-cicd.sh you@example.com
#
# Run from the repo root, AFTER your Lab 4 code is pushed to main:
# creating the stack starts a pipeline run on whatever main has.
set -euo pipefail

EMAIL="${1:?usage: bash scripts/lab4-deploy-cicd.sh you@example.com}"
GITHUB_OWNER="santiago28b"
GITHUB_REPO="cs401r-gbolano"
STACK="northstar-cicd"

ACCT=$(aws sts get-caller-identity --query Account --output text)
AB="northstar-dev-cicd-artifacts-${ACCT}"

echo "== 1. Artifacts bucket (versioned): ${AB}"
if aws s3api head-bucket --bucket "$AB" 2>/dev/null; then
  echo "   exists"
else
  aws s3api create-bucket --bucket "$AB" >/dev/null && echo "   created"
fi
aws s3api put-bucket-versioning --bucket "$AB" --versioning-configuration Status=Enabled
echo "   versioning: $(aws s3api get-bucket-versioning --bucket "$AB" --query Status --output text)"

echo "== 2. GitHub connection northstar-github"
CONN=$(aws codeconnections list-connections \
  --query "Connections[?ConnectionName=='northstar-github'].ConnectionArn | [0]" --output text)
if [ -z "$CONN" ] || [ "$CONN" = "None" ]; then
  CONN=$(aws codeconnections create-connection --provider-type GitHub \
    --connection-name northstar-github --query ConnectionArn --output text)
  echo "   created ${CONN}"
fi
STATUS=$(aws codeconnections get-connection --connection-arn "$CONN" \
  --query Connection.ConnectionStatus --output text)
echo "   status: ${STATUS}"
if [ "$STATUS" != "AVAILABLE" ]; then
  echo
  echo "   ACTION NEEDED: AWS console -> Developer Tools -> Settings -> Connections"
  echo "   -> northstar-github -> 'Update pending connection' -> authorize GitHub"
  echo "   (install the app on ${GITHUB_OWNER}/${GITHUB_REPO}). Then re-run this script."
  exit 1
fi

echo "== Spot training quota (ml.m5.large, must be >= 1)"
aws service-quotas get-service-quota --service-code sagemaker \
  --quota-code L-29688C85 --query 'Quota.Value' --output text

echo "== 6. Deploy ${STACK}"
ROLE=$(terraform -chdir=infrastructure/environments/dev output -raw ml_engineer_role_arn)
echo "   SageMakerRoleArn=${ROLE}"
aws cloudformation deploy \
  --template-file pipeline.yaml --stack-name "$STACK" \
  --parameter-overrides \
    ProjectName=northstar Environment=dev \
    GitHubOwner="$GITHUB_OWNER" GitHubRepo="$GITHUB_REPO" \
    GitHubBranch=main ArtifactsBucket="$AB" \
    GitHubConnectionArn="$CONN" \
    SageMakerRoleArn="$ROLE" \
  --capabilities CAPABILITY_NAMED_IAM

TOPIC=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ModelApprovalTopicArn'].OutputValue" --output text)
echo "== SNS topic ${TOPIC}"
SUB=$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" \
  --query "Subscriptions[?Endpoint=='${EMAIL}'].SubscriptionArn | [0]" --output text)
if [ -z "$SUB" ] || [ "$SUB" = "None" ]; then
  aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$EMAIL" >/dev/null
  SUB="PendingConfirmation"
fi
echo "   subscription for ${EMAIL}: ${SUB}"
[ "$SUB" = "PendingConfirmation" ] && echo "   ACTION NEEDED: click the confirmation link in the email from AWS Notifications."
echo
echo "Done. The stack's first pipeline run has started on main."
