"""Local schema and security validation; never provisions AWS resources."""
import json
from pathlib import Path
import cfnlint.api
import guardpycfn

HERE = Path(__file__).resolve().parent


def main():
    template = (HERE/'template.generated.json').read_text(encoding='utf-8')
    findings = cfnlint.api.lint(template, config={'regions': ['us-east-2']})
    print(json.dumps([{'rule': f.rule.id, 'message': f.message, 'path': f.path} for f in findings], indent=2))
    if any(f.rule.id.startswith('E') for f in findings): raise RuntimeError('Schema validation failed')
    for name in ['security.guard', 'ec2_instance_profile_attached.guard', 'encrypted_volumes.guard']:
        result = guardpycfn.validate_with_guard(template, (HERE/name).read_text(encoding='utf-8'), verbose=True)
        status = result.get('result', {}).get('container', {}).get('FileCheck', {}).get('status')
        print(json.dumps({'rules': name, 'status': status, 'success': result.get('success')}))
        if not result.get('success') or status == 'FAIL': raise RuntimeError('Security rules failed')


if __name__ == '__main__': main()
