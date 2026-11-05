#!/usr/bin/env node
import { App, Tags, Validations } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';

import { AppStack } from '../lib/app-stack';
import { loadParameters } from '../lib/config';
import { DataStack } from '../lib/data-stack';

const app = new App();
const parametersFile = (app.node.tryGetContext('parameters') as string | undefined) ?? 'parameters.json';
const parameters = loadParameters(parametersFile);

const env = {
  account: parameters.account || process.env.CDK_DEFAULT_ACCOUNT,
  region: parameters.region || process.env.CDK_DEFAULT_REGION,
};
const prefix = parameters.projectName
  .split('-')
  .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
  .join('');

const data = new DataStack(app, `${prefix}Data`, {
  env,
  description: 'NEUROPHOBIA network and PostgreSQL database (stateful)',
  projectName: parameters.projectName,
  database: parameters.database,
});

new AppStack(app, `${prefix}App`, {
  env,
  description: 'NEUROPHOBIA backend on ECS Fargate and web on CloudFront plus S3',
  parameters,
  vpc: data.vpc,
  databaseSecret: data.databaseSecret,
  backendSecurityGroup: data.backendSecurityGroup,
  loadBalancerSecurityGroup: data.loadBalancerSecurityGroup,
  database: data.database,
});

Tags.of(app).add('project', parameters.projectName);
Tags.of(app).add('managed-by', 'aws-cdk');
Validations.of(app).addPlugins(new AwsSolutionsChecks(app, { verbose: true }));
