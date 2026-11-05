#!/usr/bin/env bash
# Creates the first administrator inside the running NP_Back task (ECS Exec).
#
# Runs "python -m app.cli create-admin" interactively: the name, e-mail and password are typed in the
# terminal and never passed as arguments. Needs the Session Manager plugin for the AWS CLI.
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/infra/aws"
PARAMETERS="${1:-parameters.json}"
command -v session-manager-plugin >/dev/null 2>&1 || {
  echo "Falta el Session Manager plugin para AWS CLI." >&2; exit 1; }

REGION="$(node -e "console.log(require(process.argv[1]).region)" "$INFRA_DIR/$PARAMETERS")"
read -r CLUSTER SERVICE CONTAINER < <(node -e '
const outputs = require(process.argv[1]);
const app = Object.entries(outputs).find(([name]) => name.endsWith("App"))[1];
console.log(app.ClusterName, app.ServiceName, app.ContainerName);
' "$INFRA_DIR/outputs.json")

TASK="$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --desired-status RUNNING \
  --region "$REGION" --query 'taskArns[0]' --output text)"
[ -n "$TASK" ] && [ "$TASK" != "None" ] || { echo "No hay ninguna tarea del backend en marcha." >&2; exit 1; }

aws ecs execute-command --cluster "$CLUSTER" --task "$TASK" --container "$CONTAINER" --region "$REGION" \
  --interactive --command "python -m app.cli create-admin"
