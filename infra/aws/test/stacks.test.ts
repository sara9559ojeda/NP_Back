import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { describe, it } from 'node:test';

import { App } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';

import { AppStack } from '../lib/app-stack';
import { DeploymentParameters, parseParameters } from '../lib/config';
import { DataStack } from '../lib/data-stack';

const EXAMPLE = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'parameters.example.json'), 'utf8')) as Record<string, unknown>;

/** A throwaway NP_Front checkout with a built index.html. */
function fakeFrontend(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'np-front-'));
  fs.mkdirSync(path.join(root, 'dist'));
  fs.writeFileSync(path.join(root, 'dist', 'index.html'), '<!doctype html><title>NEUROPHOBIA</title>');
  return root;
}

function parameters(overrides: Record<string, unknown> = {}): DeploymentParameters {
  return parseParameters({ ...EXAMPLE, frontend: { sourceDir: fakeFrontend() }, alarmEmail: 'ops@example.com', ...overrides });
}

function synth(params: DeploymentParameters): { data: Template; app: Template } {
  const app = new App();
  const env = { account: '111111111111', region: 'us-east-1' };
  const data = new DataStack(app, 'Data', { env, projectName: params.projectName, database: params.database });
  const web = new AppStack(app, 'App', {
    env,
    parameters: params,
    vpc: data.vpc,
    databaseSecret: data.databaseSecret,
    backendSecurityGroup: data.backendSecurityGroup,
    loadBalancerSecurityGroup: data.loadBalancerSecurityGroup,
    database: data.database,
  });
  return { data: Template.fromStack(data), app: Template.fromStack(web) };
}

describe('parameters', () => {
  it('accepts the example file', () => {
    assert.equal(parseParameters(EXAMPLE).database.mode, 'rds');
  });

  it('rejects an external database without a secret name', () => {
    const database = { ...(EXAMPLE.database as object), mode: 'external', externalSecretName: '' };
    assert.throws(() => parseParameters({ ...EXAMPLE, database }), /externalSecretName/);
  });

  it('rejects memory that Fargate does not offer for the CPU', () => {
    const backend = { ...(EXAMPLE.backend as object), cpu: 256, memoryMiB: 4096 };
    assert.throws(() => parseParameters({ ...EXAMPLE, backend }), /memoryMiB/);
  });
});

describe('stacks with Amazon RDS', () => {
  const { data, app } = synth(parameters());

  it('keeps the database private, encrypted and backed up', () => {
    data.hasResourceProperties('AWS::RDS::DBInstance', {
      PubliclyAccessible: false,
      StorageEncrypted: true,
      Engine: 'postgres',
      BackupRetentionPeriod: 7,
    });
    data.hasResource('AWS::RDS::DBInstance', { DeletionPolicy: 'Snapshot' });
    data.resourceCountIs('AWS::EC2::NatGateway', 0);
  });

  it('injects every secret from Secrets Manager and none as plain text', () => {
    const [task] = Object.values(app.findResources('AWS::ECS::TaskDefinition'));
    const container = task.Properties.ContainerDefinitions[0];
    const secretNames = container.Secrets.map((s: { Name: string }) => s.Name).sort();
    assert.deepEqual(secretNames, ['NP_DATABASE_SECRET', 'NP_PROXY_SECRET', 'NP_SECRET_KEY']);
    const plain = container.Environment.map((e: { Name: string }) => e.Name);
    assert.ok(!plain.some((name: string) => /SECRET|PASSWORD|DATABASE/.test(name)));
  });

  it('serves the API through an internal load balancer behind CloudFront', () => {
    app.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', { Scheme: 'internal' });
    app.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        CacheBehaviors: [Match.objectLike({ PathPattern: '/api/v1/*', ViewerProtocolPolicy: 'https-only' })],
        Origins: Match.arrayWith([
          Match.objectLike({
            OriginCustomHeaders: [Match.objectLike({ HeaderName: 'x-np-proxy-secret' })],
            VpcOriginConfig: Match.anyValue(),
          }),
        ]),
      }),
    });
    app.hasResourceProperties('AWS::ECS::Service', {
      DeploymentConfiguration: Match.objectLike({ DeploymentCircuitBreaker: { Enable: true, Rollback: true } }),
      EnableExecuteCommand: true,
    });
  });

  it('keeps the site bucket private', () => {
    app.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: { BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true },
    });
  });

  it('creates alarms and a budget when an e-mail is set', () => {
    app.resourceCountIs('AWS::Budgets::Budget', 1);
    assert.ok(Object.keys(app.findResources('AWS::CloudWatch::Alarm')).length >= 5);
  });
});

describe('stacks with an external database', () => {
  const database = { ...(EXAMPLE.database as object), mode: 'external' };
  const { data, app } = synth(parameters({ database, alarmEmail: '' }));

  it('creates no RDS instance and passes the URL secret to the backend', () => {
    data.resourceCountIs('AWS::RDS::DBInstance', 0);
    const [task] = Object.values(app.findResources('AWS::ECS::TaskDefinition'));
    const names = task.Properties.ContainerDefinitions[0].Secrets.map((s: { Name: string }) => s.Name);
    assert.ok(names.includes('NP_DATABASE_URL'));
    app.resourceCountIs('AWS::Budgets::Budget', 0);
  });
});
