import { Validations } from 'aws-cdk-lib';
import { IConstruct } from 'constructs';

/** cdk-nag rule (`AwsSolutions-IAM5`) or granular finding (`AwsSolutions-IAM5[Resource::*]`). */
export interface Finding {
  readonly id: string;
  readonly reason: string;
}

const PACK = 'AwsSolutions::';

/** Acknowledge cdk-nag findings on `scope` and its children, each with a written reason. */
export function acknowledge(scope: IConstruct, findings: readonly Finding[]): void {
  Validations.of(scope).acknowledge(...findings.map((finding) => ({ id: `${PACK}${finding.id}`, reason: finding.reason })));
}

/** Findings on the singleton helper Lambdas that aws-cdk-lib adds to a stack (log retention, bucket deployment). */
export const CDK_HELPER_LAMBDA_FINDINGS: readonly Finding[] = [
  {
    id: 'AwsSolutions-IAM4[Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole]',
    reason: 'CDK-managed helper Lambda; the AWS managed policy only allows writing its own logs.',
  },
  { id: 'AwsSolutions-L1', reason: 'The runtime of CDK-managed helper Lambdas is chosen by aws-cdk-lib.' },
];
