import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

import { acknowledge } from './nag';

import { BACKEND_ROOT, BackendParameters, DatabaseMode } from './config';
import { LOAD_BALANCER_PORT } from './data-stack';

export const CONTAINER_NAME = 'api';
export const CONTAINER_PORT = 8000;
const LIVENESS_PATH = '/api/v1/health';

/** Paths that never belong in the backend image (the CDK app itself, local tooling, docs). */
const IMAGE_EXCLUDES = ['infra', '.git', '.venv', '**/__pycache__', '**/node_modules', 'tests', 'docs', 'scripts', 'cdk.out'];

export interface BackendServiceProps {
  readonly projectName: string;
  readonly vpc: ec2.IVpc;
  readonly settings: BackendParameters;
  readonly databaseMode: DatabaseMode;
  /** RDS JSON secret (`rds`) or full NP_DATABASE_URL secret (`external`). */
  readonly databaseSecret: secretsmanager.ISecret;
  /** Shared with CloudFront, which adds it to every API request it forwards. */
  readonly proxySecret: secretsmanager.ISecret;
  readonly signingSecret: secretsmanager.ISecret;
  /** Created by the DataStack, which lets the tasks reach the database. */
  readonly securityGroup: ec2.ISecurityGroup;
  /** Created by the DataStack; accepts the CloudFront VPC origin only. */
  readonly loadBalancerSecurityGroup: ec2.ISecurityGroup;
}

/**
 * NP_Back on ECS Fargate behind an internal Application Load Balancer.
 *
 * The load balancer has no public address: only CloudFront reaches it, through a VPC origin.
 * Tasks run in public subnets with a public IP so they can pull the image and read secrets
 * without a NAT gateway; their security group only accepts traffic from the load balancer.
 * The container entrypoint runs `alembic upgrade head` before uvicorn starts, so every
 * deployment applies pending migrations before the new task receives traffic.
 */
export class BackendService extends Construct {
  readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  readonly service: ecs.FargateService;
  readonly cluster: ecs.Cluster;
  readonly container: ecs.ContainerDefinition;
  readonly targetGroup: elbv2.ApplicationTargetGroup;
  readonly logGroup: logs.LogGroup;

  constructor(scope: Construct, id: string, props: BackendServiceProps) {
    super(scope, id);
    const { settings } = props;
    const arm = settings.cpuArchitecture === 'ARM64';

    this.cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `${props.projectName}-cluster`,
      vpc: props.vpc,
      enableFargateCapacityProviders: true,
      containerInsightsV2: ecs.ContainerInsights.DISABLED,
    });

    this.logGroup = new logs.LogGroup(this, 'Logs', {
      logGroupName: `/${props.projectName}/backend`,
      retention: settings.logRetentionDays as logs.RetentionDays,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const task = new ecs.FargateTaskDefinition(this, 'Task', {
      family: `${props.projectName}-backend`,
      cpu: settings.cpu,
      memoryLimitMiB: settings.memoryMiB,
      runtimePlatform: {
        cpuArchitecture: arm ? ecs.CpuArchitecture.ARM64 : ecs.CpuArchitecture.X86_64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });

    const databaseVariable = props.databaseMode === 'rds' ? 'NP_DATABASE_SECRET' : 'NP_DATABASE_URL';
    this.container = task.addContainer('Api', {
      containerName: CONTAINER_NAME,
      image: ecs.ContainerImage.fromAsset(BACKEND_ROOT, {
        platform: arm ? Platform.LINUX_ARM64 : Platform.LINUX_AMD64,
        exclude: IMAGE_EXCLUDES,
      }),
      portMappings: [{ containerPort: CONTAINER_PORT }],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'api', logGroup: this.logGroup }),
      environment: { NP_COOKIE_SECURE: 'true', NP_LOG_LEVEL: 'INFO' },
      secrets: {
        [databaseVariable]: ecs.Secret.fromSecretsManager(props.databaseSecret),
        NP_SECRET_KEY: ecs.Secret.fromSecretsManager(props.signingSecret),
        NP_PROXY_SECRET: ecs.Secret.fromSecretsManager(props.proxySecret),
      },
      stopTimeout: Duration.seconds(30),
    });

    this.service = new ecs.FargateService(this, 'Service', {
      serviceName: `${props.projectName}-backend`,
      cluster: this.cluster,
      taskDefinition: task,
      desiredCount: settings.desiredCount,
      assignPublicIp: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [props.securityGroup],
      capacityProviderStrategies: [{ capacityProvider: settings.useSpot ? 'FARGATE_SPOT' : 'FARGATE', weight: 1 }],
      circuitBreaker: { enable: true, rollback: true },
      minHealthyPercent: 100,
      maxHealthyPercent: 200,
      // Migrations run before uvicorn listens; give them time before health checks count.
      healthCheckGracePeriod: Duration.seconds(120),
      enableExecuteCommand: true,
    });

    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      loadBalancerName: `${props.projectName}-alb`,
      vpc: props.vpc,
      internetFacing: false,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroup: props.loadBalancerSecurityGroup,
      dropInvalidHeaderFields: true,
    });

    const listener = this.loadBalancer.addListener('Http', {
      port: LOAD_BALANCER_PORT,
      protocol: elbv2.ApplicationProtocol.HTTP,
      open: false,
    });
    this.targetGroup = listener.addTargets('Api', {
      port: CONTAINER_PORT,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [this.service],
      deregistrationDelay: Duration.seconds(30),
      healthCheck: {
        path: LIVENESS_PATH,
        healthyHttpCodes: '200',
        interval: Duration.seconds(30),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
    });

    this.acknowledgePrototypeFindings(task);
  }

  private acknowledgePrototypeFindings(task: ecs.FargateTaskDefinition): void {
    acknowledge(this.loadBalancer, [
      {
        id: 'AwsSolutions-ELB2',
        reason: 'The backend writes its own access log, without personal data, to CloudWatch Logs; ALB access logs would duplicate it.',
      },
    ]);
    acknowledge(task, [
      { id: 'AwsSolutions-ECS2', reason: 'Only non-secret settings are plain environment variables; every secret comes from Secrets Manager.' },
      {
        id: 'AwsSolutions-IAM5[Resource::*]',
        reason: 'ecr:GetAuthorizationToken (execution role) and ssmmessages for ECS Exec (task role) do not support resource scoping.',
      },
    ]);
    acknowledge(this.cluster, [
      { id: 'AwsSolutions-ECS4', reason: 'Container Insights is disabled to keep the prototype cost low; service metrics and logs are still in CloudWatch.' },
    ]);
  }
}
