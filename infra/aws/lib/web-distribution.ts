import * as fs from 'node:fs';
import * as path from 'node:path';

import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

import { acknowledge } from './nag';

export const API_PATH_PATTERN = '/api/v1/*';
/** Header NP_Back trusts for the client IP only when the proxy secret header matches. */
export const CLIENT_IP_HEADER = 'x-np-client-ip';
export const PROXY_SECRET_HEADER = 'x-np-proxy-secret';

/** Viewer request on the API: replace any client-supplied IP header with the real viewer IP. */
export const CLIENT_IP_FUNCTION = `function handler(event) {
  var request = event.request;
  request.headers['${CLIENT_IP_HEADER}'] = { value: event.viewer.ip };
  return request;
}`;

/** Viewer request on the web: routes without a file extension are SPA routes served by index.html. */
export const SPA_ROUTING_FUNCTION = `function handler(event) {
  var request = event.request;
  var last = request.uri.split('/').pop();
  if (last.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}`;

export interface WebDistributionProps {
  readonly projectName: string;
  readonly loadBalancer: elbv2.IApplicationLoadBalancer;
  readonly proxySecret: secretsmanager.ISecret;
  /** Built NP_Front (`npm run build` output). */
  readonly frontendDist: string;
}

/**
 * One CloudFront domain for the web and the API.
 *
 * `/api/v1/*` goes to the internal load balancer through a VPC origin, uncached and with every
 * viewer header and cookie, so the refresh cookie stays first-party (SameSite=Strict, path
 * /api/v1/auth) exactly as with the Vercel proxy. Everything else is the static NP_Front build
 * from a private S3 bucket (origin access control).
 */
export class WebDistribution extends Construct {
  readonly distribution: cloudfront.Distribution;
  readonly bucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: WebDistributionProps) {
    super(scope, id);

    if (!fs.existsSync(path.join(props.frontendDist, 'index.html'))) {
      throw new Error(`NP_Front build not found in ${props.frontendDist}. Run "npm run build" in NP_Front first.`);
    }

    this.bucket = new s3.Bucket(this, 'Site', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      // Only the rebuildable static site lives here; teardown must leave nothing behind.
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const api = origins.VpcOrigin.withApplicationLoadBalancer(props.loadBalancer, {
      vpcOriginName: `${props.projectName}-api`,
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      httpPort: 80,
      readTimeout: Duration.seconds(30),
      customHeaders: { [PROXY_SECRET_HEADER]: props.proxySecret.secretValue.unsafeUnwrap() },
    });

    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      comment: `${props.projectName} web and API`,
      defaultRootObject: 'index.html',
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(this.bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        functionAssociations: [this.viewerFunction('SpaRouting', SPA_ROUTING_FUNCTION, 'Serve index.html for SPA routes')],
      },
      additionalBehaviors: {
        [API_PATH_PATTERN]: {
          origin: api,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
          responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
          compress: true,
          functionAssociations: [this.viewerFunction('ClientIp', CLIENT_IP_FUNCTION, 'Forward the viewer IP to NP_Back')],
        },
      },
    });

    new s3deploy.BucketDeployment(this, 'Deploy', {
      sources: [s3deploy.Source.asset(props.frontendDist)],
      destinationBucket: this.bucket,
      distribution: this.distribution,
      distributionPaths: ['/*'],
      // Revalidate on every visit; Vite already fingerprints the asset file names.
      cacheControl: [s3deploy.CacheControl.fromString('public, max-age=0, must-revalidate')],
      memoryLimit: 512,
    });

    acknowledge(this.bucket, [
      { id: 'AwsSolutions-S1', reason: 'Static, rebuildable site content; CloudFront is the only reader.' },
    ]);
    acknowledge(this.distribution, [
      { id: 'AwsSolutions-CFR1', reason: 'The prototype serves every country; no geo restriction requirement.' },
      { id: 'AwsSolutions-CFR2', reason: 'AWS WAF (about 6 USD per month) is optional for the prototype; NP_Back applies its own rate limits. Documented as a follow-up.' },
      { id: 'AwsSolutions-CFR3', reason: 'NP_Back logs every API request to CloudWatch; static file logs are not needed for the prototype.' },
      { id: 'AwsSolutions-CFR4', reason: 'The default CloudFront certificate is used until a custom domain exists; it only negotiates TLS 1.2 or later with modern clients.' },
    ]);
  }

  private viewerFunction(id: string, code: string, comment: string): cloudfront.FunctionAssociation {
    const fn = new cloudfront.Function(this, id, {
      code: cloudfront.FunctionCode.fromInline(code),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
      comment,
    });
    return { function: fn, eventType: cloudfront.FunctionEventType.VIEWER_REQUEST };
  }
}
