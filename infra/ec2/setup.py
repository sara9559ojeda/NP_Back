"""Runs as root on EC2; secrets are read through the instance profile, never logged."""
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path('/opt/neurophobia')
CONFIG = BASE / 'config'
REGION = 'us-east-2'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    os.umask(0o077)
    CONFIG.mkdir(exist_ok=True, mode=0o700)
    names = ['db_password', 'app_password', 'secret_key', 'proxy_secret']
    data = json.loads(subprocess.check_output(['aws', 'ssm', 'get-parameters', '--with-decryption', '--region', REGION, '--names', *['/neurophobia/ec2/' + n for n in names]]))
    values = {p['Name'].rsplit('/', 1)[1]: p['Value'] for p in data['Parameters']}
    if len(values) != 4: raise RuntimeError('Missing required secure parameters')
    def envfile(name, fields):
        path = CONFIG / name
        path.write_text(''.join(f'{key}={value}\n' for key, value in fields.items()))
        path.chmod(0o600)
    envfile('database.env', {'POSTGRES_USER': 'np_owner', 'POSTGRES_DB': 'neurophobia', 'POSTGRES_PASSWORD': values['db_password']})
    common = {'NP_SECRET_KEY': values['secret_key'], 'NP_PROXY_SECRET': values['proxy_secret'], 'NP_COOKIE_SECURE': 'true', 'NP_LOG_LEVEL': 'INFO'}
    envfile('owner.env', {**common, 'NP_DATABASE_URL': f"postgresql+psycopg://np_owner:{values['db_password']}@np-db:5432/neurophobia"})
    envfile('runtime.env', {**common, 'NP_DATABASE_URL': f"postgresql+psycopg://np_app:{values['app_password']}@np-db:5432/neurophobia"})
    existing = subprocess.check_output(['docker', 'network', 'ls', '--format', '{{.Name}}']).decode().splitlines()
    if 'np-internal' not in existing: run('docker', 'network', 'create', '--internal', 'np-internal')
    if 'np-api-network' not in existing: run('docker', 'network', 'create', 'np-api-network')
    containers = subprocess.check_output(['docker', 'ps', '-a', '--format', '{{.Names}}']).decode().splitlines()
    logs = ['--log-opt', 'max-size=10m', '--log-opt', 'max-file=3']
    if 'np-db' not in containers:
        run('docker', 'run', '-d', '--name', 'np-db', '--restart', 'unless-stopped', '--memory', '768m', '--network', 'np-internal', '--env-file', str(CONFIG/'database.env'), '-v', 'np-pgdata:/var/lib/postgresql/data', *logs, 'postgres:17.9-alpine', '-c', 'max_connections=50', '-c', 'shared_buffers=128MB')
    else: run('docker', 'start', 'np-db')
    for _ in range(60):
        if subprocess.run(['docker', 'exec', 'np-db', 'pg_isready', '-U', 'np_owner', '-d', 'neurophobia'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0: break
        time.sleep(2)
    else: raise RuntimeError('PostgreSQL failed readiness')
    run('docker', 'run', '--rm', '--network', 'np-internal', '--env-file', str(CONFIG/'owner.env'), '--entrypoint', 'alembic', 'neurophobia-api:ec2-20261109', 'upgrade', 'head')
    # Passwords are random URL-safe tokens; bind them as literals without printing SQL.
    grant = f"""DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='np_app') THEN CREATE ROLE np_app LOGIN PASSWORD '{values['app_password']}'; END IF; END $$;
GRANT CONNECT ON DATABASE neurophobia TO np_app;
GRANT USAGE ON SCHEMA identity, clinical TO np_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity, clinical TO np_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA identity, clinical TO np_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity, clinical GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO np_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA identity, clinical GRANT USAGE, SELECT ON SEQUENCES TO np_app;
"""
    subprocess.run(['docker', 'exec', '-i', 'np-db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'np_owner', '-d', 'neurophobia'], input=grant.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if 'np-api' in containers:
        networks = json.loads(subprocess.check_output(['docker', 'inspect', 'np-api']))[0]['NetworkSettings']['Networks']
        if 'np-api-network' not in networks:
            # Replace only the stateless API container; preserve the database volume.
            run('docker', 'rm', '-f', 'np-api')
            containers.remove('np-api')
    if 'np-api' not in containers:
        run('docker', 'create', '--name', 'np-api', '--restart', 'unless-stopped', '--memory', '512m', '--network', 'np-api-network', '--env-file', str(CONFIG/'runtime.env'), '-p', '127.0.0.1:8000:8000', *logs, '--entrypoint', 'uvicorn', 'neurophobia-api:ec2-20261109', 'app.main:create_app', '--factory', '--host', '0.0.0.0', '--port', '8000', '--no-access-log', '--no-proxy-headers')
        run('docker', 'network', 'connect', 'np-internal', 'np-api')
        run('docker', 'start', 'np-api')
    else: run('docker', 'start', 'np-api')
    nginx = (BASE/'infra/nginx.conf').read_text().replace('__PROXY_SECRET__', values['proxy_secret'])
    nginx_path = Path('/etc/nginx/conf.d/neurophobia.conf')
    nginx_path.write_text(nginx)
    # Nginx master is root; workers receive the parsed proxy configuration.
    nginx_path.chmod(0o600)
    # Remove the distribution's default server to ensure the application handles requests.
    main_config = Path('/etc/nginx/nginx.conf')
    main_config.write_text('user nginx; worker_processes auto; error_log /var/log/nginx/error.log warn; pid /run/nginx.pid; events { worker_connections 1024; } http { include /etc/nginx/mime.types; default_type application/octet-stream; sendfile on; include /etc/nginx/conf.d/*.conf; }\n')
    run('nginx', '-t')
    run('systemctl', 'enable', '--now', 'nginx')
    run('systemctl', 'reload', 'nginx')
    print('Database migrations and services configured')


if __name__ == '__main__': main()
