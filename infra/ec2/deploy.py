"""EC2 always-on deployment, confined to the existing AWS Free project and Ohio."""
import argparse
import base64
import hashlib
import json
import secrets
import subprocess
import tarfile
from pathlib import Path

import boto3
from botocore.config import Config

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / '.build'
STACK = 'neurophobia-ec2'
REGION = 'us-east-2'
IMAGE = 'neurophobia-api:ec2-20261109'
ref = lambda name: {'Ref': name}
attr = lambda name, field: {'Fn::GetAtt': [name, field]}
sub = lambda value: {'Fn::Sub': value}


def make_template(bucket, key, ami, prefix):
    resources = {}
    def add(name, kind, properties, why, **extra):
        resources[name] = {'Type': kind, 'Properties': properties, 'Metadata': {'com.aws.cloudformation.Context': {'why': why, 'must': ['Region us-east-2; retain persistent data; no Lambda or RDS']}}, **extra}
    add('Vpc', 'AWS::EC2::VPC', {'CidrBlock': '10.44.0.0/16', 'EnableDnsSupport': True, 'EnableDnsHostnames': True}, 'Dedicated network for the academic server')
    add('Gateway', 'AWS::EC2::InternetGateway', {}, 'Required for outbound package downloads and CloudFront VPC origins')
    add('AttachGateway', 'AWS::EC2::VPCGatewayAttachment', {'VpcId': ref('Vpc'), 'InternetGatewayId': ref('Gateway')}, 'Connect outbound traffic without a paid NAT gateway')
    add('Subnet', 'AWS::EC2::Subnet', {'VpcId': ref('Vpc'), 'CidrBlock': '10.44.0.0/24', 'MapPublicIpOnLaunch': True}, 'Single-AZ cost constraint; inbound access is restricted by security group')
    add('RouteTable', 'AWS::EC2::RouteTable', {'VpcId': ref('Vpc')}, 'Dedicated outbound route table')
    add('DefaultRoute', 'AWS::EC2::Route', {'RouteTableId': ref('RouteTable'), 'DestinationCidrBlock': '0.0.0.0/0', 'GatewayId': ref('Gateway')}, 'Outbound downloads and SSM', DependsOn='AttachGateway')
    add('RouteAssociation', 'AWS::EC2::SubnetRouteTableAssociation', {'SubnetId': ref('Subnet'), 'RouteTableId': ref('RouteTable')}, 'Apply the outbound routing to the server')
    ingress = {'Fn::If': ['Hardened', {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'SourceSecurityGroupId': ref('CloudFrontSg')}, {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'SourcePrefixListId': prefix}]}
    add('ServerSecurityGroup', 'AWS::EC2::SecurityGroup', {'GroupDescription': 'CloudFront only; no SSH or PostgreSQL inbound', 'VpcId': ref('Vpc'), 'SecurityGroupIngress': [ingress], 'SecurityGroupEgress': [{'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'CidrIp': '0.0.0.0/0'}, {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'CidrIp': '0.0.0.0/0'}]}, 'Initially accepts CloudFront prefix list; narrowed to the service-managed SG before release')
    statements = [
        {'Effect': 'Allow', 'Action': ['s3:GetObject'], 'Resource': [f'arn:aws:s3:::{bucket}/deployments/*', f'arn:aws:s3:::{bucket}/backups/*']},
        {'Effect': 'Allow', 'Action': ['s3:PutObject'], 'Resource': f'arn:aws:s3:::{bucket}/backups/*'},
        {'Effect': 'Allow', 'Action': ['s3:ListBucket'], 'Resource': f'arn:aws:s3:::{bucket}', 'Condition': {'StringLike': {'s3:prefix': ['backups/*', 'deployments/*']}}},
        {'Effect': 'Allow', 'Action': ['ssm:GetParameters'], 'Resource': sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/neurophobia/ec2/*')},
        {'Effect': 'Allow', 'Action': ['cloudwatch:PutMetricData'], 'Resource': '*', 'Condition': {'StringEquals': {'cloudwatch:namespace': 'Neurophobia/Operations'}}},
    ]
    add('ServerRole', 'AWS::IAM::Role', {'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': 'sts:AssumeRole', 'Principal': {'Service': 'ec2.amazonaws.com'}}]}, 'ManagedPolicyArns': ['arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'], 'Policies': [{'PolicyName': 'ApplicationOperations', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': statements}}]}, 'Instance profile for SSM, scoped artifacts, backups, secure parameters and health metrics')
    add('Profile', 'AWS::IAM::InstanceProfile', {'Roles': [ref('ServerRole')]}, 'No static AWS access keys on disk')
    script = (HERE/'bootstrap.sh').read_text(encoding='utf-8').replace('__BUCKET__', bucket).replace('__ARTIFACT__', key)
    add('Server', 'AWS::EC2::Instance', {'ImageId': ami, 'InstanceType': 't3.small', 'IamInstanceProfile': ref('Profile'), 'SubnetId': ref('Subnet'), 'SecurityGroupIds': [ref('ServerSecurityGroup')], 'CreditSpecification': {'CPUCredits': 'standard'}, 'MetadataOptions': {'HttpTokens': 'required', 'HttpEndpoint': 'enabled', 'HttpPutResponseHopLimit': 1}, 'DisableApiTermination': True, 'InstanceInitiatedShutdownBehavior': 'stop', 'BlockDeviceMappings': [{'DeviceName': '/dev/xvda', 'Ebs': {'VolumeSize': 20, 'VolumeType': 'gp3', 'Encrypted': True, 'DeleteOnTermination': False}}], 'UserData': base64.b64encode(script.encode()).decode(), 'Tags': [{'Key': 'Name', 'Value': STACK}, {'Key': 'Project', 'Value': 'neurophobia'}]}, 'Continuously running backend and PostgreSQL; no idle suspension or surplus CPU charges', DependsOn=['DefaultRoute', 'RouteAssociation'], DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
    add('VpcOrigin', 'AWS::CloudFront::VpcOrigin', {'VpcOriginEndpointConfig': {'Name': STACK, 'Arn': sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:instance/${Server}'), 'HTTPPort': 80, 'HTTPSPort': 443, 'OriginProtocolPolicy': 'http-only', 'OriginSSLProtocols': ['TLSv1.2']}}, 'Private AWS network between CloudFront and EC2; viewer traffic uses HTTPS', DependsOn='AttachGateway')
    add('IpFunction', 'AWS::CloudFront::Function', {'Name': STACK+'-client-ip', 'AutoPublish': True, 'FunctionConfig': {'Comment': 'Replace client IP with verified CloudFront viewer IP', 'Runtime': 'cloudfront-js-2.0'}, 'FunctionCode': "function handler(event) { event.request.headers['x-np-client-ip']={value:event.viewer.ip}; return event.request; }"}, 'Do not trust caller-supplied forwarding headers')
    associations = [{'EventType': 'viewer-request', 'FunctionARN': attr('IpFunction', 'FunctionARN')}]
    behavior = {'TargetOriginId': 'server', 'ViewerProtocolPolicy': 'redirect-to-https', 'AllowedMethods': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'], 'CachedMethods': ['GET', 'HEAD'], 'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad', 'OriginRequestPolicyId': 'b689b0a8-53d0-40ab-baf2-68738e2966ac', 'ResponseHeadersPolicyId': '67f7725c-6f97-4210-82d7-5512b31e9d03', 'Compress': True, 'FunctionAssociations': associations}
    add('Distribution', 'AWS::CloudFront::Distribution', {'DistributionConfig': {'Enabled': True, 'Comment': 'Neurophobia EC2 continuous academic deployment', 'DefaultRootObject': 'index.html', 'PriceClass': 'PriceClass_100', 'HttpVersion': 'http2and3', 'IPV6Enabled': True, 'ViewerCertificate': {'CloudFrontDefaultCertificate': True}, 'Origins': [{'Id': 'server', 'DomainName': attr('Server', 'PrivateDnsName'), 'VpcOriginConfig': {'VpcOriginId': attr('VpcOrigin', 'Id'), 'OriginReadTimeout': 30}}], 'DefaultCacheBehavior': behavior}}, 'One HTTPS origin for web, cookies and visor; cache disabled for authenticated responses')
    for logical, metric, namespace, dimensions, comparison, threshold, period, evaluation in [
        ('HostRecovery', 'StatusCheckFailed_System', 'AWS/EC2', [{'Name': 'InstanceId', 'Value': ref('Server')}], 'GreaterThanThreshold', 0, 60, 2),
        ('BackupAlarm', 'BackupSuccess', 'Neurophobia/Operations', [], 'LessThanThreshold', 1, 86400, 2),
        ('DiskAlarm', 'DiskUsedPercent', 'Neurophobia/Operations', [], 'GreaterThanThreshold', 80, 300, 2),
    ]:
        props = {'AlarmDescription': 'Check CloudWatch console; no email subscription configured', 'Namespace': namespace, 'MetricName': metric, 'Dimensions': dimensions, 'Statistic': 'Maximum', 'Period': period, 'EvaluationPeriods': evaluation, 'Threshold': threshold, 'ComparisonOperator': comparison, 'TreatMissingData': 'breaching' if logical == 'BackupAlarm' else 'missing'}
        if logical == 'HostRecovery': props['AlarmActions'] = [sub('arn:${AWS::Partition}:automate:${AWS::Region}:ec2:recover')]
        add(logical, 'AWS::CloudWatch::Alarm', props, 'Automatic host recovery or operational visibility; no scheduled shutdown')
    return {'AWSTemplateFormatVersion': '2010-09-09', 'Description': 'Always-on EC2 and PostgreSQL for four months of academic use within existing Free plan credits; no Lambda or RDS.', 'Metadata': {'AWSToolsMetrics': {'AWSAgentToolkit': 'aws-cloudformation@3'}}, 'Parameters': {'CloudFrontSg': {'Type': 'String', 'Default': ''}}, 'Conditions': {'Hardened': {'Fn::Not': [{'Fn::Equals': [ref('CloudFrontSg'), '']}]}}, 'Resources': resources, 'Outputs': {'InstanceId': {'Value': ref('Server')}, 'VpcId': {'Value': ref('Vpc')}, 'SecurityGroupId': {'Value': ref('ServerSecurityGroup')}, 'WebUrl': {'Value': sub('https://${Distribution.DomainName}')}, 'DistributionId': {'Value': ref('Distribution')}, 'StorageBucket': {'Value': bucket}}}


def session_clients():
    session = boto3.Session(profile_name='neurophobia', region_name=REGION)
    config = Config(retries={'mode': 'standard', 'max_attempts': 6}, connect_timeout=10, read_timeout=60)
    return session, {name: session.client(name, config=config) for name in ['s3', 'ssm', 'cloudformation', 'ec2', 'sts', 'freetier']}


def outputs(cf):
    stack = cf.describe_stacks(StackName=STACK)['Stacks'][0]
    return stack, {item['OutputKey']: item['OutputValue'] for item in stack.get('Outputs', [])}


def prepare():
    BUILD.mkdir(exist_ok=True)
    subprocess.run(['docker', 'save', '-o', str(BUILD/'image.tar'), IMAGE], check=True)
    with tarfile.open(BUILD/'release.tar.gz', 'w:gz') as archive:
        archive.add(BUILD/'image.tar', arcname='image.tar')
        frontend = ROOT.parent / 'NP_Front/dist'
        if not (frontend / 'index.html').is_file():
            raise RuntimeError('Build NP_Front before preparing the deployment')
        for file in frontend.rglob('*'):
            if file.is_file() and file.name != 'mockServiceWorker.js':
                archive.add(file, arcname='frontend/'+file.relative_to(frontend).as_posix())
        for name in ['setup.py', 'nginx.conf', 'security-headers.conf', 'backup.sh', 'health.sh', 'create_admin.py', 'restore_check.sh']:
            archive.add(HERE/name, arcname='infra/'+name)
    print(json.dumps({'artifactBytes': (BUILD/'release.tar.gz').stat().st_size}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'plan', 'deploy', 'status', 'harden', 'command', 'command-result', 'apk'])
    p.add_argument('--command')
    p.add_argument('--command-id')
    p.add_argument('--apk-path', type=Path)
    args = p.parse_args()
    if args.action == 'prepare': return prepare()
    session, clients = session_clients()
    cf, s3, ssm, ec2 = (clients[n] for n in ['cloudformation', 's3', 'ssm', 'ec2'])
    account = clients['sts'].get_caller_identity()['Account']
    bucket = f'{STACK}-{account}-{REGION}'
    artifact = BUILD/'release.tar.gz'
    key = 'deployments/'+hashlib.file_digest(artifact.open('rb'), 'sha256').hexdigest()+'.tar.gz' if artifact.exists() else 'deployments/pending.tar.gz'
    ami = ssm.get_parameter(Name='/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64')['Parameter']['Value']
    prefix = ec2.describe_managed_prefix_lists(Filters=[{'Name': 'prefix-list-name', 'Values': ['com.amazonaws.global.cloudfront.origin-facing']}])['PrefixLists'][0]['PrefixListId']
    document = make_template(bucket, key, ami, prefix)
    text = json.dumps(document)
    (HERE/'template.generated.json').write_text(text, encoding='utf-8')
    if args.action == 'plan':
        print(json.dumps({'template': str(HERE/'template.generated.json'), 'serviceValidation': cf.validate_template(TemplateBody=text)['Capabilities'], 'plan': clients['freetier'].get_account_plan_state()}, default=str, indent=2))
    elif args.action == 'deploy':
        plan = clients['freetier'].get_account_plan_state()
        if plan['accountPlanType'] != 'FREE' or plan['accountPlanStatus'] != 'ACTIVE' or float(plan['accountPlanRemainingCredits']['amount']) < 90:
            raise RuntimeError('Expected active FREE project with at least 90 USD credit; no resources created')
        cf.validate_template(TemplateBody=text)
        existing = {b['Name'] for page in s3.get_paginator('list_buckets').paginate() for b in page['Buckets']}
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={'LocationConstraint': REGION})
        s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={k: True for k in ['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets']})
        s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
        s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={'Status': 'Enabled'})
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*', 'Resource': [f'arn:aws:s3:::{bucket}', f'arn:aws:s3:::{bucket}/*'], 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}))
        s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={'Rules': [{'ID': 'daily-backups', 'Status': 'Enabled', 'Filter': {'Prefix': 'backups/'}, 'Expiration': {'Days': 14}, 'NoncurrentVersionExpiration': {'NoncurrentDays': 7}}, {'ID': 'old-artifact-versions', 'Status': 'Enabled', 'Filter': {'Prefix': ''}, 'NoncurrentVersionExpiration': {'NoncurrentDays': 30}, 'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1}}]})
        for name in ['db_password', 'app_password', 'secret_key', 'proxy_secret']:
            parameter = '/neurophobia/ec2/'+name
            try: ssm.get_parameter(Name=parameter)
            except ssm.exceptions.ParameterNotFound:
                ssm.put_parameter(Name=parameter, Type='SecureString', Value=secrets.token_urlsafe(48), Description='Neurophobia EC2 secret; do not expose in logs')
        s3.upload_file(str(artifact), bucket, key, ExtraArgs={'ServerSideEncryption': 'AES256'})
        existing_stacks = [s for page in cf.get_paginator('list_stacks').paginate() for s in page['StackSummaries'] if s['StackName'] == STACK and s['StackStatus'] != 'DELETE_COMPLETE']
        if existing_stacks: raise RuntimeError('Stack exists; inspect changes before any update')
        result = cf.create_stack(StackName=STACK, TemplateBody=text, Capabilities=['CAPABILITY_IAM'], EnableTerminationProtection=True, Tags=[{'Key': 'Project', 'Value': 'neurophobia'}])
        print(json.dumps({'stack': result['StackId']}))
    elif args.action == 'status':
        stack, out = outputs(cf)
        print(json.dumps({'status': stack['StackStatus'], 'outputs': out}, indent=2))
        if out: (HERE/'outputs.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
        else:
            print(json.dumps([{k: e.get(k) for k in ['LogicalResourceId', 'ResourceStatus', 'ResourceStatusReason']} for e in cf.describe_stack_events(StackName=STACK)['StackEvents'][:10]], indent=2))
    elif args.action == 'harden':
        stack, out = outputs(cf)
        groups = ec2.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [out['VpcId']]}, {'Name': 'group-name', 'Values': ['CloudFront-VPCOrigins-Service-SG*']}])['SecurityGroups']
        if len(groups) != 1: raise RuntimeError('Expected one service-managed CloudFront security group')
        cf.update_stack(StackName=STACK, UsePreviousTemplate=True, Parameters=[{'ParameterKey': 'CloudFrontSg', 'ParameterValue': groups[0]['GroupId']}], Capabilities=['CAPABILITY_IAM'])
        print('Narrowed inbound access to CloudFront VPC service security group')
    elif args.action == 'command':
        _, out = outputs(cf)
        if 'InstanceId' not in out:
            out['InstanceId'] = cf.describe_stack_resource(StackName=STACK, LogicalResourceId='Server')['StackResourceDetail']['PhysicalResourceId']
        result = ssm.send_command(InstanceIds=[out['InstanceId']], DocumentName='AWS-RunShellScript', Parameters={'commands': [args.command]}, TimeoutSeconds=600, Comment='Neurophobia authorized deployment verification')
        print(result['Command']['CommandId'])
    elif args.action == 'command-result':
        _, out = outputs(cf)
        if 'InstanceId' not in out:
            out['InstanceId'] = cf.describe_stack_resource(StackName=STACK, LogicalResourceId='Server')['StackResourceDetail']['PhysicalResourceId']
        result = ssm.get_command_invocation(CommandId=args.command_id, InstanceId=out['InstanceId'])
        print(json.dumps({k: result.get(k) for k in ['Status', 'ResponseCode', 'StandardOutputContent', 'StandardErrorContent']}, indent=2))
    elif args.action == 'apk':
        if not args.apk_path or args.apk_path.suffix.lower() != '.apk': raise ValueError('Provide --apk-path')
        with args.apk_path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        apk_key = 'releases/'+digest[:16]+'/neurophobia.apk'
        s3.upload_file(str(args.apk_path), bucket, apk_key, ExtraArgs={'ContentType': 'application/vnd.android.package-archive', 'ContentDisposition': 'attachment; filename="neurophobia.apk"', 'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': digest}})
        manifest = {'key': apk_key, 'sha256': digest, 'bytes': args.apk_path.stat().st_size, 'backendConfiguration': 'Configure backend_url.txt with WebUrl before use; headset test pending'}
        s3.put_object(Bucket=bucket, Key='releases/latest.json', Body=json.dumps(manifest).encode(), ContentType='application/json', ServerSideEncryption='AES256')
        print(json.dumps(manifest, indent=2))


if __name__ == '__main__': main()
