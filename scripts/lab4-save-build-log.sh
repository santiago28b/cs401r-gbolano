#!/usr/bin/env bash
# Save the FULL CodeBuild log of the latest northstar-pipeline run to a file.
#   bash scripts/lab4-save-build-log.sh docs/lab4-build-green.log
#   bash scripts/lab4-save-build-log.sh docs/lab4-build-failed.log [execution-id]
set -euo pipefail
OUT="${1:?usage: bash scripts/lab4-save-build-log.sh docs/<name>.log}"
CP=northstar-pipeline
# Optional 2nd arg: a specific CodePipeline execution id (default: latest).
EX="${2:-$(aws codepipeline list-pipeline-executions --pipeline-name "$CP" --max-items 1 \
  --query 'pipelineExecutionSummaries[0].pipelineExecutionId' --output text | head -1)}"
BID=$(aws codepipeline list-action-executions --pipeline-name "$CP" --filter pipelineExecutionId="$EX" \
  --query "actionExecutionDetails[?actionName=='RunTestsAndTrain'].output.executionResult.externalExecutionId | [0]" \
  --output text)
G=$(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].logs.groupName' --output text)
S=$(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].logs.streamName' --output text)
{
  echo "# CodePipeline execution: $EX"
  echo "# CodeBuild build:        $BID ($(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].buildStatus' --output text))"
  echo "# Source commit:          $(aws codebuild batch-get-builds --ids "$BID" --query 'builds[0].resolvedSourceVersion' --output text)"
  echo "# Saved:                  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  TOKEN=""
  while :; do
    if [ -z "$TOKEN" ]; then
      R=$(aws logs get-log-events --log-group-name "$G" --log-stream-name "$S" --start-from-head --output json)
    else
      R=$(aws logs get-log-events --log-group-name "$G" --log-stream-name "$S" --start-from-head --next-token "$TOKEN" --output json)
    fi
    echo "$R" | python3 -c 'import json,sys; [print(e["message"].rstrip("\n")) for e in json.load(sys.stdin)["events"]]'
    NEXT=$(echo "$R" | python3 -c 'import json,sys; print(json.load(sys.stdin)["nextForwardToken"])')
    [ "$NEXT" = "$TOKEN" ] && break
    TOKEN="$NEXT"
  done
} > "$OUT"
echo "Saved $(wc -l < "$OUT") lines to $OUT"
grep -nE "passed|failed|PASSED|FAILED|SKIPPED|champion v|FAIRNESS" "$OUT" | tail -25 || true
