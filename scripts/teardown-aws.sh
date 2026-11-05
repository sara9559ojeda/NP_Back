#!/usr/bin/env bash
# Removes the NEUROPHOBIA AWS deployment created by deploy-aws.sh.
#
#   scripts/teardown-aws.sh [--parameters parameters.json]
#
# Destroys the application stack, lifts the termination protection of the data stack and destroys
# it. Amazon RDS keeps a final snapshot (it still costs storage until you delete it). The CDKToolkit
# bootstrap stack is kept because other CDK apps in the account may use it.
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/infra/aws"
PARAMETERS="parameters.json"
[ "${1:-}" = "--parameters" ] && PARAMETERS="$2"

param() { node -e "const p=require(process.argv[1]); console.log(p[process.argv[2]])" "$INFRA_DIR/$PARAMETERS" "$1"; }
PROJECT="$(param projectName)"
REGION="$(param region)"
PREFIX="$(node -e "console.log(process.argv[1].split('-').map(p => p[0].toUpperCase() + p.slice(1)).join(''))" "$PROJECT")"

echo "Se borraran las pilas ${PREFIX}App y ${PREFIX}Data en $REGION, con la base de datos."
echo "RDS guardara una instantanea final. Los datos de la web dejaran de estar disponibles."
read -r -p "Escribe '$PROJECT' para confirmar: " ANSWER
[ "$ANSWER" = "$PROJECT" ] || { echo "Cancelado."; exit 1; }

cd "$INFRA_DIR"
npx cdk destroy "${PREFIX}App" -c "parameters=$PARAMETERS" --force
aws cloudformation update-termination-protection --no-enable-termination-protection \
  --stack-name "${PREFIX}Data" --region "$REGION" >/dev/null
npx cdk destroy "${PREFIX}Data" -c "parameters=$PARAMETERS" --force
echo "Listo. Revisa las instantaneas en RDS > Snapshots si quieres borrarlas tambien."
