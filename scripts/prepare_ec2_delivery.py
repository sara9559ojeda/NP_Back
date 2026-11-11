"""Package an already built image and web output without contacting AWS."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def git(repository: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repository), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='neurophobia-api:academic-delivery')
    args = parser.parse_args()
    frontend = ROOT.parent / 'NP_Front'
    for repository in (ROOT, frontend):
        if git(repository, 'status', '--porcelain'):
            raise RuntimeError('Commit and verify the source before packaging')
    if not (frontend / 'dist/index.html').is_file():
        raise RuntimeError('Build the web application first')
    output = ROOT / 'infra/ec2/.build/delivery'
    output.mkdir(parents=True, exist_ok=True)
    image_id = subprocess.check_output(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}'], text=True).strip()
    subprocess.run(['docker', 'save', '-o', str(output / 'image.tar'), image_id], check=True)
    with tarfile.open(output / 'frontend.tar.gz', 'w:gz') as archive:
        for path in sorted((frontend / 'dist').rglob('*')):
            if path.is_file() and path.name != 'mockServiceWorker.js':
                archive.add(path, arcname=path.relative_to(frontend / 'dist').as_posix())
    with tarfile.open(output / 'operations.tar.gz', 'w:gz') as archive:
        for name in ('update_runtime.py', 'nginx.conf', 'security-headers.conf'):
            archive.add(ROOT / 'infra/ec2' / name, arcname=name)
        archive.add(ROOT / 'docs/ENTREGA_EC2.md', arcname='ENTREGA_EC2.md')
    checksums = {}
    for name in ('image.tar', 'frontend.tar.gz', 'operations.tar.gz'):
        with (output / name).open('rb') as stream:
            checksums[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {
        'backendCommit': git(ROOT, 'rev-parse', 'HEAD'),
        'frontendCommit': git(frontend, 'rev-parse', 'HEAD'),
        'imageId': image_id,
        'checksums': checksums,
        'deployed': False,
    }
    (output / 'delivery.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in checksums.items()), encoding='utf-8')
    print(json.dumps({'directory': str(output), **manifest}))


if __name__ == '__main__':
    main()
