#!/bin/bash
# Restore into a temporary database; never overwrite the application database.
set -euo pipefail
source /etc/neurophobia-operations
key=$(aws s3api list-objects-v2 --bucket "$NP_BUCKET" --prefix backups/ --query 'sort_by(Contents,&LastModified)[-1].Key' --output text --region us-east-2)
test "$key" != None
target="np_restorecheck_$(date +%s)"
docker exec np-db createdb -U np_owner "$target"
trap 'docker exec np-db dropdb -U np_owner "$target"' EXIT
aws s3 cp "s3://$NP_BUCKET/$key" - --region us-east-2 --only-show-errors | docker exec -i np-db pg_restore -U np_owner -d "$target" --no-owner --no-privileges --exit-on-error
for database in neurophobia "$target"; do
    docker exec np-db psql -At -U np_owner -d "$database" -c "SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname IN ('identity','clinical') ORDER BY 1" > "/tmp/$database.tables"
done
cmp /tmp/neurophobia.tables "/tmp/$target.tables"
while IFS= read -r table; do
    live=$(docker exec np-db psql -At -U np_owner -d neurophobia -c "SELECT count(*) FROM $table")
    restored=$(docker exec np-db psql -At -U np_owner -d "$target" -c "SELECT count(*) FROM $table")
    test "$live" = "$restored"
done < /tmp/neurophobia.tables
rm -f /tmp/neurophobia.tables "/tmp/$target.tables"
echo 'Backup restoration passed: application tables and row counts match'
