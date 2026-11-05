import { Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

import { acknowledge, CDK_HELPER_LAMBDA_FINDINGS } from './nag';

import { DatabaseParameters } from './config';

export interface DataStackProps extends StackProps {
  readonly projectName: string;
  readonly database: DatabaseParameters;
}

const DATABASE_NAME = 'neurophobia';
const DATABASE_USER = 'neurophobia';
export const LOAD_BALANCER_PORT = 80;

/**
 * Stateful layer: the network and the PostgreSQL database.
 *
 * Kept in its own stack with termination protection so an application change can never replace
 * or delete clinical data. The VPC has no NAT gateway (cost); the database lives in isolated
 * subnets with no route to the internet.
 */
export class DataStack extends Stack {
  readonly vpc: ec2.Vpc;
  /** RDS instance, or undefined when the backend uses an external database. */
  readonly database?: rds.DatabaseInstance;
  /** Secret the backend reads: the RDS JSON secret, or the external NP_DATABASE_URL secret. */
  readonly databaseSecret: secretsmanager.ISecret;
  /**
   * Security groups of the load balancer and the backend tasks. They live here, next to the
   * database rule that trusts them, so the stateful stack never depends on the application stack.
   */
  readonly loadBalancerSecurityGroup: ec2.SecurityGroup;
  readonly backendSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, { ...props, terminationProtection: true });

    this.vpc = new ec2.Vpc(this, 'Network', {
      vpcName: `${props.projectName}-network`,
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
      flowLogs: {
        rejected: {
          destination: ec2.FlowLogDestination.toCloudWatchLogs(
            new logs.LogGroup(this, 'FlowLogs', {
              retention: logs.RetentionDays.ONE_MONTH,
              removalPolicy: RemovalPolicy.DESTROY,
            }),
          ),
          trafficType: ec2.FlowLogTrafficType.REJECT,
        },
      },
    });

    this.loadBalancerSecurityGroup = new ec2.SecurityGroup(this, 'LoadBalancerSecurityGroup', {
      vpc: this.vpc,
      description: 'Internal load balancer reached only by the CloudFront VPC origin',
      allowAllOutbound: false,
    });
    // CloudFront VPC origin network interfaces live inside this VPC.
    this.loadBalancerSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(this.vpc.vpcCidrBlock),
      ec2.Port.tcp(LOAD_BALANCER_PORT),
      'CloudFront VPC origin',
    );
    acknowledge(this.loadBalancerSecurityGroup, [
      { id: 'AwsSolutions-EC23', reason: 'Ingress is limited to the VPC CIDR (CloudFront VPC origin interfaces); the load balancer is internal.' },
    ]);

    this.backendSecurityGroup = new ec2.SecurityGroup(this, 'BackendSecurityGroup', {
      vpc: this.vpc,
      description: 'NP_Back tasks; inbound only from the internal load balancer',
      allowAllOutbound: true,
    });

    acknowledge(this, [
      ...CDK_HELPER_LAMBDA_FINDINGS,
      { id: 'AwsSolutions-IAM5[Resource::*]', reason: 'CDK log retention helper sets retention on log groups whose names are only known at deploy time.' },
    ]);

    if (props.database.mode === 'rds') {
      this.database = this.createDatabase(props);
      this.database.connections.allowDefaultPortFrom(this.backendSecurityGroup, 'NP_Back tasks');
      this.databaseSecret = this.database.secret!;
    } else {
      this.databaseSecret = secretsmanager.Secret.fromSecretNameV2(
        this,
        'ExternalDatabaseUrl',
        props.database.externalSecretName,
      );
    }
  }

  private createDatabase(props: DataStackProps): rds.DatabaseInstance {
    const settings = props.database;
    const database = new rds.DatabaseInstance(this, 'Database', {
      instanceIdentifier: `${props.projectName}-db`,
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_17_9 }),
      instanceType: new ec2.InstanceType(settings.instanceClass),
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      publiclyAccessible: false,
      databaseName: DATABASE_NAME,
      credentials: rds.Credentials.fromGeneratedSecret(DATABASE_USER, {
        secretName: `${props.projectName}/database`,
      }),
      multiAz: settings.multiAz,
      storageType: rds.StorageType.GP3,
      allocatedStorage: settings.allocatedStorageGiB,
      maxAllocatedStorage: settings.maxAllocatedStorageGiB,
      storageEncrypted: true,
      caCertificate: rds.CaCertificate.RDS_CA_RSA2048_G1,
      backupRetention: Duration.days(settings.backupRetentionDays),
      preferredBackupWindow: '07:00-07:30',
      preferredMaintenanceWindow: 'sun:08:00-sun:08:30',
      autoMinorVersionUpgrade: true,
      copyTagsToSnapshot: true,
      deletionProtection: settings.deletionProtection,
      removalPolicy: RemovalPolicy.SNAPSHOT,
      cloudwatchLogsExports: ['postgresql'],
      cloudwatchLogsRetention: logs.RetentionDays.ONE_MONTH,
      parameters: {
        // PostgreSQL 15+ on RDS already defaults to this; stating it documents the TLS requirement.
        'rds.force_ssl': '1',
        // Slow statements only; parameters are not logged (no personal data in the logs).
        log_min_duration_statement: '1000',
      },
    });

    acknowledge(database, [
      {
        id: 'AwsSolutions-SMG4',
        reason: 'Rotation needs a Lambda in the VPC plus VPC endpoints; out of scope for the academic prototype and documented as a follow-up.',
      },
      { id: 'AwsSolutions-RDS3', reason: 'Multi-AZ is a parameter (database.multiAz); single AZ keeps the prototype cost low.' },
      { id: 'AwsSolutions-RDS10', reason: 'Deletion protection is a parameter; the stack has termination protection and a final snapshot.' },
      { id: 'AwsSolutions-RDS11', reason: 'The default port is only reachable from the backend security group inside isolated subnets.' },
    ]);
    return database;
  }
}
