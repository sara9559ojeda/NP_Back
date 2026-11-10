"""Prepare locally, then run on the EC2 host; no password appears in command arguments."""
import argparse
import json
import secrets
import subprocess
from pathlib import Path

PARAMETER = '/neurophobia/ec2/admin_bootstrap'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'create'])
    parser.add_argument('--email')
    parser.add_argument('--name')
    parser.add_argument('--credential-file', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        import boto3
        if not args.email or not args.name or not args.credential_file: raise ValueError('Email, name and protected local destination required')
        ssm = boto3.Session(profile_name='neurophobia', region_name='us-east-2').client('ssm')
        if args.credential_file.exists(): raise RuntimeError('Credentials already prepared; do not rotate implicitly')
        data = {'email': args.email, 'full_name': args.name, 'password': secrets.token_urlsafe(24)}
        ssm.put_parameter(Name=PARAMETER, Type='SecureString', Value=json.dumps(data), Overwrite=False, Description='One-time admin bootstrap; delete after creation')
        args.credential_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Initial credentials saved to the protected local file; not printed')
    else:
        data = json.loads(subprocess.check_output(['aws', 'ssm', 'get-parameter', '--name', PARAMETER, '--with-decryption', '--region', 'us-east-2']))['Parameter']['Value']
        code = '''import json,sys
from app.db.session import _session_factory
from app.services.auth import create_account
from app.repositories.identity import get_user_by_email
data=json.load(sys.stdin)
with _session_factory()() as db:
    user=get_user_by_email(db,data['email'])
    if user is None:
        create_account(db,email=data['email'],password=data['password'],role='admin',full_name=data['full_name'])
        db.commit()
    elif user.role != 'admin':
        raise RuntimeError('Existing account is not an administrator')
print('Administrator created or already present')
'''
        subprocess.run(['docker', 'exec', '-i', 'np-api', 'python', '-c', code], input=data.encode(), check=True)


if __name__ == '__main__': main()
