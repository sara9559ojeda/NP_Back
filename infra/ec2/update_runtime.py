"""Update the existing EC2 API locally, retaining the previous container for rollback."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from urllib.request import urlopen

BASE = Path('/opt/neurophobia')
CONFIG = BASE / 'config'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True, help='Loaded immutable sha256 image ID')
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r'sha256:[a-f0-9]{64}', args.image):
        raise RuntimeError('Run as root with a verified immutable image ID')
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = BASE / 'backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    for filename in ('owner.env', 'runtime.env'):
        path = CONFIG / filename
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise RuntimeError('Required environment file is missing or not private')
    with (backup / 'database.dump').open('wb') as stream:
        run('docker', 'exec', 'np-db', 'pg_dump', '-U', 'np_owner', '-d', 'neurophobia', '-Fc', stdout=stream)
    run('docker', 'run', '--rm', '--network', 'np-internal', '--env-file', str(CONFIG / 'owner.env'),
        '--entrypoint', 'alembic', args.image, 'upgrade', '0004')
    grant = ('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA clinical TO np_app;'
             'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA clinical TO np_app;')
    run('docker', 'exec', '-i', 'np-db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'np_owner', '-d', 'neurophobia',
        input=grant.encode(), stdout=subprocess.DEVNULL)
    extra_env = []
    groq = CONFIG / 'groq.env'
    if groq.exists():
        if groq.stat().st_mode & 0o077:
            raise RuntimeError('groq.env must have mode 600')
        extra_env = ['--env-file', str(groq)]
    releases = BASE / 'releases'
    releases.mkdir(exist_ok=True, mode=0o755)
    previous = 'np-api-rollback-' + stamp
    run('docker', 'stop', 'np-api', stdout=subprocess.DEVNULL)
    run('docker', 'rename', 'np-api', previous)
    try:
        run('docker', 'create', '--name', 'np-api', '--restart', 'unless-stopped', '--memory', '512m',
            '--network', 'np-api-network', '--env-file', str(CONFIG / 'runtime.env'), *extra_env,
            '-e', 'NP_APK_RELEASE_DIRECTORY=/srv/releases', '-v', str(releases) + ':/srv/releases:ro',
            '-p', '127.0.0.1:8000:8000', '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3',
            '--entrypoint', 'uvicorn', args.image, 'app.main:create_app', '--factory',
            '--host', '0.0.0.0', '--port', '8000', '--no-access-log', '--no-proxy-headers', stdout=subprocess.DEVNULL)
        run('docker', 'network', 'connect', 'np-internal', 'np-api')
        run('docker', 'start', 'np-api', stdout=subprocess.DEVNULL)
        for _ in range(20):
            try:
                with urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=2) as response:
                    if response.status == 200:
                        print(json.dumps({'status': 'ready', 'image': args.image, 'rollbackContainer': previous,
                                          'databaseBackup': str(backup / 'database.dump')}))
                        return
            except OSError:
                pass
            time.sleep(2)
        raise RuntimeError('Updated API did not become ready')
    except BaseException:
        subprocess.run(['docker', 'rm', '-f', 'np-api'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run('docker', 'rename', previous, 'np-api')
        run('docker', 'start', 'np-api', stdout=subprocess.DEVNULL)
        raise


if __name__ == '__main__':
    main()
