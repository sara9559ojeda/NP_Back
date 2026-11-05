import { Duration } from 'aws-cdk-lib';
import * as budgets from 'aws-cdk-lib/aws-budgets';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import { Construct } from 'constructs';

const FIVE_MINUTES = Duration.minutes(5);
const MIN_FREE_STORAGE_BYTES = 2 * 1024 ** 3;

export interface MonitoringProps {
  readonly projectName: string;
  /** Receives alarm and budget e-mails. */
  readonly email: string;
  readonly monthlyBudgetUsd: number;
  readonly service: ecs.FargateService;
  readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  readonly targetGroup: elbv2.ApplicationTargetGroup;
  readonly database?: rds.DatabaseInstance;
}

/** E-mail alarms for the signals that mean "the system is down" plus a monthly cost budget. */
export class Monitoring extends Construct {
  readonly topic: sns.Topic;

  constructor(scope: Construct, id: string, props: MonitoringProps) {
    super(scope, id);

    this.topic = new sns.Topic(this, 'Alarms', {
      topicName: `${props.projectName}-alarms`,
      enforceSSL: true,
    });
    this.topic.addSubscription(new subscriptions.EmailSubscription(props.email));

    this.alarm('Api5xx', 'Backend answered 5xx more than 5 times in 5 minutes',
      props.loadBalancer.metrics.httpCodeTarget(elbv2.HttpCodeTarget.TARGET_5XX_COUNT, { period: FIVE_MINUTES, statistic: 'Sum' }),
      5, cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD);
    this.alarm('UnhealthyTargets', 'No healthy backend task for 15 minutes',
      props.targetGroup.metrics.healthyHostCount({ period: FIVE_MINUTES, statistic: 'Minimum' }),
      1, cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD, 3, cloudwatch.TreatMissingData.BREACHING);
    this.alarm('BackendCpu', 'Backend CPU above 80 percent for 15 minutes',
      props.service.metricCpuUtilization({ period: FIVE_MINUTES }),
      80, cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD, 3);

    if (props.database) {
      this.alarm('DatabaseCpu', 'Database CPU above 80 percent for 15 minutes',
        props.database.metricCPUUtilization({ period: FIVE_MINUTES }),
        80, cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD, 3);
      this.alarm('DatabaseStorage', 'Database free storage below 2 GiB',
        props.database.metricFreeStorageSpace({ period: FIVE_MINUTES }),
        MIN_FREE_STORAGE_BYTES, cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD);
    }

    this.budget(props);
  }

  private alarm(
    id: string,
    description: string,
    metric: cloudwatch.IMetric,
    threshold: number,
    comparisonOperator: cloudwatch.ComparisonOperator,
    evaluationPeriods = 1,
    treatMissingData = cloudwatch.TreatMissingData.NOT_BREACHING,
  ): void {
    const alarm = new cloudwatch.Alarm(this, id, {
      alarmDescription: description,
      metric,
      threshold,
      comparisonOperator,
      evaluationPeriods,
      treatMissingData,
    });
    alarm.addAlarmAction(new actions.SnsAction(this.topic));
    alarm.addOkAction(new actions.SnsAction(this.topic));
  }

  private budget(props: MonitoringProps): void {
    const subscriber = { subscriptionType: 'EMAIL', address: props.email };
    new budgets.CfnBudget(this, 'Budget', {
      budget: {
        budgetName: `${props.projectName}-monthly`,
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: props.monthlyBudgetUsd, unit: 'USD' },
      },
      notificationsWithSubscribers: [
        {
          notification: { notificationType: 'ACTUAL', comparisonOperator: 'GREATER_THAN', threshold: 80, thresholdType: 'PERCENTAGE' },
          subscribers: [subscriber],
        },
        {
          notification: { notificationType: 'FORECASTED', comparisonOperator: 'GREATER_THAN', threshold: 100, thresholdType: 'PERCENTAGE' },
          subscribers: [subscriber],
        },
      ],
    });
  }
}
