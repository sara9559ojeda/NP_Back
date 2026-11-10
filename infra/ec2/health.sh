#!/bin/bash
set -euo pipefail
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
aws cloudwatch put-metric-data --namespace Neurophobia/Operations --metric-data MetricName=DiskUsedPercent,Value="$used",Unit=Percent --region us-east-2
if ! curl -fsS --max-time 15 http://127.0.0.1:8000/api/v1/health/ready >/dev/null; then
    sleep 5
    if ! curl -fsS --max-time 15 http://127.0.0.1:8000/api/v1/health/ready >/dev/null; then
        docker restart np-api >/dev/null
    fi
fi
