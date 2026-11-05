import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as vm from 'node:vm';

import { CLIENT_IP_FUNCTION, SPA_ROUTING_FUNCTION } from '../lib/web-distribution';

interface CloudFrontRequest {
  uri: string;
  headers: Record<string, { value: string }>;
}

type Handler = (event: { request: CloudFrontRequest; viewer: { ip: string } }) => CloudFrontRequest;

function load(code: string): Handler {
  const context: { handler?: Handler } = {};
  vm.runInNewContext(`${code}\nthis.handler = handler;`, context);
  return context.handler!;
}

function run(code: string, uri: string, headers: CloudFrontRequest['headers'] = {}): CloudFrontRequest {
  return load(code)({ request: { uri, headers }, viewer: { ip: '203.0.113.7' } });
}

describe('SPA routing function', () => {
  it('rewrites client routes to index.html', () => {
    for (const uri of ['/', '/login', '/pacientes/123', '/admin/usuarios/']) {
      assert.equal(run(SPA_ROUTING_FUNCTION, uri).uri, '/index.html', uri);
    }
  });

  it('keeps real files', () => {
    for (const uri of ['/assets/index-abc123.js', '/favicon.svg', '/index.html']) {
      assert.equal(run(SPA_ROUTING_FUNCTION, uri).uri, uri);
    }
  });
});

describe('client IP function', () => {
  it('overwrites any IP header the client sent', () => {
    const request = run(CLIENT_IP_FUNCTION, '/api/v1/auth/login', { 'x-np-client-ip': { value: '10.0.0.1' } });
    assert.equal(request.headers['x-np-client-ip'].value, '203.0.113.7');
  });
});
