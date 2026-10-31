#!/usr/bin/env bash
# Lab 4 evidence capture. Appends to docs/, never overwrites.
#
#   bash scripts/lab4-evidence.sh run  "run 1: first green run"
#       -> docs/lab4-pipeline-runs.txt  (latest CodePipeline execution: commit,
#          phases, pytest counts, SageMaker steps, where it stopped)
#
#   bash scripts/lab4-evidence.sh demo "BEFORE: alarm in OK"
#       -> docs/lab4-failure-demo.txt   (same run summary + alarm state +
#          describe-alarm-history Action + Model Registry versions)
#
# Run from the repo root after the Build stage of the run has finished.
set -uo pipefail

MODE="${1:?usage: bash scripts/lab4-evidence.sh run|demo \"label\"}"
LABEL="${2:-}"
CP=northstar-pipeline
SMP=northstar-churn-pipeline
GROUP=northstar-churn-models
ALARM=northstar-ci-build-failure

case "$MODE" in
  run)  OUT=docs/lab4-pipeline-runs.txt ;;
  demo) OUT=docs/lab4-failure-demo.txt ;;
  *) echo "mode must be run or demo"; exit 2 ;;
esac

registry() {
  echo "-- Model Registry: ${GROUP} (newest first)"
  aws sagemaker list-model-packages --model-package-group-name "$GROUP" \
    --sort-by CreationTime --sort-order Descending --max-results 10 \
    --query "ModelPackageSummaryList[].[ModelPackageVersion,ModelApprovalStatus,CreationTime]" \
    --output table
}

run_summary() {
  local EX ID BID
  EX=$(aws codepipeline list-pipeline-executions --pipeline-name "$CP" --max-items 1 \
    --query 'pipelineExecutionSummaries[0].[pipelineExecutionId,status,startTime,sourceRevisions[0].revisionId,sourceRevisions[0].revisionSummary]' \
    --output text)
  ID=$(echo "$EX" | cut -f1)
  echo "-- CodePipeline ${CP} execution ${ID}"
  echo "   status:  $(echo "$EX" | cut -f2)   started: $(echo "$EX" | cut -f3)"
  echo "   commit:  $(echo "$EX" | cut -f4)"
  echo "   message: $(echo "$EX" | cut -f5- | head -1)"
  echo "-- CodePipeline stages (Source -> Build -> ManualApproval)"
  aws codepipeline list-action-executions --pipeline-name "$CP" \
    --filter pipelineExecutionId="$ID" \
    --query 'actionExecutionDetails[].[stageName,actionName,status]' --output table

  BID=$(aws codepipeline list-action-executions --pipeline-name "$CP" \
    --filter pipelineExecutionId="$ID" \
    --query "actionExecutionDetails[?actionName=='RunTestsAndTrain'].output.executionResult.externalExecutionId | [0]" \
    --output text)
  if [ -z "$BID" ] || [ "$BID" = "None" ]; then echo "   (no CodeBuild build yet)"; return; fi
  echo "-- CodeBuild ${BID}: $(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].buildStatus' --output text)"
  echo "   phases (the run stops at the first FAILED phase):"
  aws codebuild batch-get-builds --ids "$BID" \
    --query 'builds[0].phases[].[phaseType,phaseStatus,durationInSeconds]' --output table

  local G S
  G=$(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].logs.groupName' --output text)
  S=$(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].logs.streamName' --output text)
  echo "-- Key lines from the build log (pytest summaries, gate, registration)"
  aws logs filter-log-events --log-group-name "$G" --log-stream-names "$S" \
    --filter-pattern '?"passed" ?"failed" ?"FAILED" ?"error" ?"Pipeline status" ?"Registered" ?"Training job" ?"FAIRNESS" ?"Champion" ?"Rejected" ?"PHASE"' \
    --query 'events[].message' --output text | tr '\t' '\n' | grep -v '^\s*$' | tail -60

  echo "-- Latest SageMaker Pipeline execution (${SMP})"
  local PEX
  PEX=$(aws sagemaker list-pipeline-executions --pipeline-name "$SMP" --max-results 1 \
    --query 'PipelineExecutionSummaries[0].[PipelineExecutionArn,PipelineExecutionStatus,PipelineExecutionDisplayName,StartTime]' \
    --output text 2>/dev/null)
  echo "   ${PEX}"
  if [ -n "$PEX" ] && [ "$PEX" != "None" ]; then
    aws sagemaker list-pipeline-execution-steps --pipeline-execution-arn "$(echo "$PEX" | cut -f1)" \
      --query 'PipelineExecutionSteps[].[StepName,StepStatus,FailureReason]' --output table
  fi
}

{
  echo
  echo "=================================================================="
  echo "${LABEL}"
  echo "captured $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "=================================================================="
  run_summary
  if [ "$MODE" = "demo" ]; then
    echo "-- Alarm ${ALARM}"
    aws cloudwatch describe-alarms --alarm-names "$ALARM" \
      --query 'MetricAlarms[0].[StateValue,StateUpdatedTimestamp,StateReason]' --output text
    echo "-- describe-alarm-history --history-item-type Action (did SNS get it?)"
    aws cloudwatch describe-alarm-history --alarm-name "$ALARM" \
      --history-item-type Action --max-records 5 \
      --query 'AlarmHistoryItems[].[Timestamp,HistorySummary]' --output text
    echo "-- NorthStar/CI BuildSucceeded (absent = died before the gate)"
    aws cloudwatch get-metric-statistics --namespace NorthStar/CI --metric-name BuildSucceeded \
      --dimensions Name=Project,Value=northstar-ci \
      --start-time "$(date -u -v-3H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '3 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
      --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --period 300 --statistics Minimum \
      --query 'sort_by(Datapoints,&Timestamp)[].[Timestamp,Minimum]' --output text
  fi
  registry
} 2>&1 | tee -a "$OUT"

echo
echo "Appended to ${OUT}"
