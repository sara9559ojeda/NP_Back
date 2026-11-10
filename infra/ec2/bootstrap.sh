#!/bin/bash
set -euo pipefail
umask 022
dnf install -y docker nginx python3
systemctl enable --now docker amazon-ssm-agent
mkdir -p /opt/neurophobia
aws s3 cp "s3://__BUCKET__/__ARTIFACT__" /opt/neurophobia/artifact.tar.gz --region us-east-2 --only-show-errors
expected=$(basename '__ARTIFACT__' .tar.gz)
echo "$expected  /opt/neurophobia/artifact.tar.gz" | sha256sum --check --status
tar -xzf /opt/neurophobia/artifact.tar.gz -C /opt/neurophobia
docker load -i /opt/neurophobia/image.tar >/dev/null
docker pull postgres:17.9-alpine
python3 /opt/neurophobia/infra/setup.py
rm -f /opt/neurophobia/image.tar /opt/neurophobia/artifact.tar.gz
printf 'NP_BUCKET=%s\n' '__BUCKET__' > /etc/neurophobia-operations
chmod 600 /etc/neurophobia-operations
chmod 700 /opt/neurophobia/infra/backup.sh /opt/neurophobia/infra/health.sh
cat > /etc/systemd/system/neurophobia-backup.service <<'EOF'
[Unit]
Description=Daily encrypted PostgreSQL backup to S3
After=docker.service network-online.target
[Service]
Type=oneshot
ExecStart=/bin/bash /opt/neurophobia/infra/backup.sh
EOF
cat > /etc/systemd/system/neurophobia-backup.timer <<'EOF'
[Unit]
Description=Daily PostgreSQL backup
[Timer]
OnCalendar=*-*-* 03:00:00 UTC
RandomizedDelaySec=900
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/neurophobia-health.service <<'EOF'
[Unit]
Description=Application health and disk usage
After=docker.service network-online.target
[Service]
Type=oneshot
ExecStart=/bin/bash /opt/neurophobia/infra/health.sh
EOF
cat > /etc/systemd/system/neurophobia-health.timer <<'EOF'
[Unit]
Description=Check application health every five minutes
[Timer]
OnBootSec=120
OnUnitActiveSec=300
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now neurophobia-backup.timer neurophobia-health.timer
systemctl start neurophobia-backup.service
touch /opt/neurophobia/BOOTSTRAP_COMPLETE
