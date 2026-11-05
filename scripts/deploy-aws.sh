#!/usr/bin/env bash
# Deploys NEUROPHOBIA (NP_Back + NP_Front) to AWS with the CDK app in infra/aws.
#
#   scripts/deploy-aws.sh [--yes] [--parameters parameters.json]
#
# 1. Checks the tools and the AWS credentials.
# 2. Builds NP_Front against the real API (/api/v1, no mocks).
# 3. Bootstraps CDK in the target account and Region (idempotent).
# 4. Runs cdk deploy for both stacks and prints the URLs.
# Nothing secret is read or printed: the stacks generate or read every secret in Secrets Manager.
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$BACKEND_ROOT/infra/aws"
PARAMETERS="parameters.json"
APPROVAL="broadening"

while [ $# -gt 0 ]; do
  case "$1" in
    --yes) APPROVAL="never" ;;
    --parameters) PARAMETERS="$2"; shift ;;
    *) echo "Opcion desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$1"; }
fail() { echo "ERROR: $1" >&2; exit 1; }
require() { command -v "$1" >/dev/null 2>&1 || fail "Falta '$1'. $2"; }
param() { node -e "const p=require(process.argv[1]); console.log(process.argv[2].split('.').reduce((o,k)=>o[k],p) ?? '')" "$INFRA_DIR/$PARAMETERS" "$1"; }

require aws "Instala AWS CLI v2."
require node "Instala Node.js 20.19 o superior."
require npm "Instala Node.js 20.19 o superior."
require docker "Instala Docker y arrancalo."
docker info >/dev/null 2>&1 || fail "Docker no esta en marcha."

[ -f "$INFRA_DIR/$PARAMETERS" ] || fail "No existe infra/aws/$PARAMETERS. Copia parameters.example.json y revisalo."
REGION="$(param region)"
FRONTEND_DIR="$BACKEND_ROOT/$(param frontend.sourceDir)"
[ -f "$FRONTEND_DIR/package.json" ] || fail "No se encuentra NP_Front en $FRONTEND_DIR (frontend.sourceDir)."

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" \
  || fail 'No hay credenciales de AWS validas. Ejecuta "aws configure" o "aws sso login".'
EXPECTED="$(param account)"
[ -z "$EXPECTED" ] || [ "$EXPECTED" = "$ACCOUNT" ] || fail "Las credenciales son de $ACCOUNT, pero parameters.json pide $EXPECTED."
echo "Cuenta $ACCOUNT, region $REGION"

if [ "$(param database.mode)" = "external" ]; then
  SECRET_NAME="$(param database.externalSecretName)"
  aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" --query Name --output text >/dev/null 2>&1 \
    || fail "No existe el secreto '$SECRET_NAME' en $REGION. Crealo primero (docs/DESPLIEGUE_AWS.md)."
fi

step "Instalando dependencias de la infraestructura"
(cd "$INFRA_DIR" && npm ci --no-audit --no-fund)

step "Compilando NP_Front contra la API real"
(cd "$FRONTEND_DIR" && npm ci --no-audit --no-fund && VITE_API_BASE_URL=/api/v1 VITE_USE_MOCKS=false npm run build)

export CDK_DEFAULT_ACCOUNT="$ACCOUNT" CDK_DEFAULT_REGION="$REGION"
cd "$INFRA_DIR"
step "Preparando CDK en la cuenta (bootstrap)"
npx cdk bootstrap "aws://$ACCOUNT/$REGION" -c "parameters=$PARAMETERS"

step "Desplegando (puede tardar 15-25 minutos la primera vez)"
npx cdk deploy --all -c "parameters=$PARAMETERS" --require-approval "$APPROVAL" --outputs-file outputs.json

node -e '
const outputs = require(process.argv[1]);
const app = Object.entries(outputs).find(([name]) => name.endsWith("App"))[1];
console.log("\nDespliegue terminado.");
console.log("  Web:              " + app.WebUrl);
console.log("  API (Unity):      " + app.ApiBaseUrl);
console.log("  Logs del backend: " + app.BackendLogGroup);
console.log("\nSiguiente paso: crear el primer administrador con scripts/aws-create-admin.sh");
' "$INFRA_DIR/outputs.json"
