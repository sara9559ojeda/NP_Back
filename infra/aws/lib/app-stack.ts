import * as path from 'node:path';

import { CfnOutput, Stack, StackProps } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

import { acknowledge, CDK_HELPER_LAMBDA_FINDINGS } from './nag';

import { BackendService, CONTAINER_NAME } from './backend-service';
import { BACKEND_ROOT, DeploymentParameters } from './config';
import { Monitoring } from './monitoring';
import { WebDistribution } from './web-distribution';

export interface AppStackProps extends StackProps {
  readonly parameters: DeploymentParameters;
  readonly vpc: ec2.IVpc;
  readonly databaseSecret: secretsmanager.ISecret;
  readonly backendSecurityGroup: ec2.ISecurityGroup;
  readonly loadBalancerSecurityGroup: ec2.ISecurityGroup;
  readonly database?: rds.DatabaseInstance;
}

/**
 * Stateless layer: backend service, web distribution, application secrets and monitoring.
 *
 * It can be destroyed and recreated freely; the data lives in the DataStack.
 */
export class AppStack extends Stack {
  constructor(scope: Construct, id: string, props: AppStackProps) {
    super(scope, id, props);
    const { parameters } = props;
    const name = parameters.projectName;

    const signingSecret = this.generatedSecret('SigningKey', `${name}/secret-key`, 'NP_SECRET_KEY: signs the web access tokens');
    const proxySecret = this.generatedSecret('ProxySecret', `${name}/proxy-secret`, 'NP_PROXY_SECRET: shared by CloudFront and NP_Back');

    const backend = new BackendService(this, 'Backend', {
      projectName: name,
      vpc: props.vpc,
      settings: parameters.backend,
      databaseMode: parameters.database.mode,
      databaseSecret: props.databaseSecret,
      proxySecret,
      signingSecret,
      securityGroup: props.backendSecurityGroup,
      loadBalancerSecurityGroup: props.loadBalancerSecurityGroup,
    });

    const web = new WebDistribution(this, 'Web', {
      projectName: name,
      loadBalancer: backend.loadBalancer,
      proxySecret,
      frontendDist: path.resolve(BACKEND_ROOT, parameters.frontend.sourceDir, 'dist'),
    });
    const origin = `https://${web.distribution.distributionDomainName}`;
    backend.container.addEnvironment('NP_CORS_ORIGIN', origin);

    if (parameters.alarmEmail) {
      new Monitoring(this, 'Monitoring', {
        projectName: name,
        email: parameters.alarmEmail,
        monthlyBudgetUsd: parameters.monthlyBudgetUsd,
        service: backend.service,
        loadBalancer: backend.loadBalancer,
        targetGroup: backend.targetGroup,
        database: props.database,
      });
    }

    new CfnOutput(this, 'WebUrl', { value: origin, description: 'NP_Front for patients, professionals and administrators' });
    new CfnOutput(this, 'ApiBaseUrl', { value: `${origin}/api/v1`, description: 'API base URL for the Unity app (ApiBaseUrl)' });
    new CfnOutput(this, 'ClusterName', { value: backend.cluster.clusterName, description: 'ECS cluster (ECS Exec, create-admin)' });
    new CfnOutput(this, 'ServiceName', { value: backend.service.serviceName, description: 'ECS service of NP_Back' });
    new CfnOutput(this, 'ContainerName', { value: CONTAINER_NAME, description: 'Container name for ECS Exec' });
    new CfnOutput(this, 'BackendLogGroup', { value: backend.logGroup.logGroupName, description: 'CloudWatch Logs of NP_Back' });
    new CfnOutput(this, 'DistributionId', { value: web.distribution.distributionId, description: 'CloudFront distribution' });

    this.acknowledgeCdkManagedFindings();
  }

  private generatedSecret(id: string, secretName: string, description: string): secretsmanager.Secret {
    const secret = new secretsmanager.Secret(this, id, {
      secretName,
      description,
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
    });
    acknowledge(secret, [
      {
        id: 'AwsSolutions-SMG4',
        reason: 'Rotating this key signs every user out, or breaks the CloudFront header until the next deploy; it is rotated manually as documented.',
      },
    ]);
    return secret;
  }

  /** Findings on resources that aws-cdk-lib itself creates (BucketDeployment, auto-delete objects). */
  private acknowledgeCdkManagedFindings(): void {
    acknowledge(this, [
      ...CDK_HELPER_LAMBDA_FINDINGS,
      ...['s3:Abort*', 's3:DeleteObject*', 's3:GetBucket*', 's3:GetObject*', 's3:List*'].map((action) => ({
        id: `AwsSolutions-IAM5[Action::${action}]`,
        reason: 'BucketDeployment grant on the site bucket and the CDK asset bucket only.',
      })),
      {
        id: 'AwsSolutions-IAM5[Resource::<WebSiteD504717C.Arn>/*]',
        reason: 'BucketDeployment writes every object of the site bucket.',
      },
      {
        id: 'AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:s3:::cdk-hnb659fds-assets-<AWS::AccountId>-<AWS::Region>/*]',
        reason: 'BucketDeployment reads the zipped site from the CDK bootstrap asset bucket.',
      },
      {
        id: `AwsSolutions-IAM5[Resource::arn:<AWS::Partition>:s3:::cdk-hnb659fds-assets-<AWS::AccountId>-${this.region}/*]`,
        reason: 'BucketDeployment reads the zipped site from the CDK bootstrap asset bucket.',
      },
      {
        id: 'AwsSolutions-IAM5[Resource::*]',
        reason: 'BucketDeployment calls cloudfront:CreateInvalidation, which aws-cdk-lib grants on all distributions.',
      },
      { id: 'AwsSolutions-SNS2', reason: 'CloudWatch alarms cannot publish to a topic encrypted with the AWS managed key; alarms carry no personal data.' },
    ]);
  }
}
