#!/bin/bash
set -euo pipefail
source /etc/neurophobia-operations
stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
if docker exec np-db pg_dump -U np_owner -d neurophobia -Fc | aws s3 cp - "s3://$NP_BUCKET/backups/$stamp.dump" --region us-east-2 --sse AES256 --only-show-errors; then
    aws cloudwatch put-metric-data --namespace Neurophobia/Operations --metric-data MetricName=BackupSuccess,Value=1,Unit=Count --region us-east-2
    echo "Backup uploaded successfully: $stamp"
else
    aws cloudwatch put-metric-data --namespace Neurophobia/Operations --metric-data MetricName=BackupSuccess,Value=0,Unit=Count --region us-east-2
    exit 1
fi
