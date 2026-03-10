import { expect, test } from '@playwright/test';
import { resolveAdminUrl, resolveGatewayWebSocketUrl, resolveKernelApiUrl, resolveKernelBaseUrl } from '../lib/deployment-endpoints';

test.afterEach(() => {
  delete process.env.NEXT_PUBLIC_KERNEL_BASE_URL;
  delete process.env.NEXT_PUBLIC_GATEWAY_WS_URL;
});

test('admin endpoints default to same-origin relative paths when no kernel base url is configured', () => {
  expect(resolveKernelBaseUrl()).toBe('');
  expect(resolveAdminUrl('/api/admin/runtime-overview')).toBe('/api/admin/runtime-overview');
  expect(resolveAdminUrl('api/admin/llm-config')).toBe('/api/admin/llm-config');
});

test('admin endpoints prefer explicit kernel base url when provided', () => {
  process.env.NEXT_PUBLIC_KERNEL_BASE_URL = 'https://api.example.com/';

  expect(resolveKernelBaseUrl()).toBe('https://api.example.com');
  expect(resolveAdminUrl('/api/admin/runtime-overview')).toBe('https://api.example.com/api/admin/runtime-overview');
});

test('library and task endpoints share the same deployment-friendly kernel resolution', () => {
  expect(resolveKernelApiUrl('/api/library/import-latest')).toBe('/api/library/import-latest');
  expect(resolveKernelApiUrl('/api/tasks/task-123/cancel')).toBe('/api/tasks/task-123/cancel');

  process.env.NEXT_PUBLIC_KERNEL_BASE_URL = 'https://api.example.com/';

  expect(resolveKernelApiUrl('/api/library/import-latest')).toBe('https://api.example.com/api/library/import-latest');
  expect(resolveKernelApiUrl('/api/tasks/task-123/cancel')).toBe('https://api.example.com/api/tasks/task-123/cancel');
});

test('websocket url is inferred from the current page origin when no explicit gateway url is configured', () => {
  expect(resolveGatewayWebSocketUrl({ protocol: 'http:', host: 'demo.example.com:3000' })).toBe(
    'ws://demo.example.com:3000/ws'
  );
  expect(resolveGatewayWebSocketUrl({ protocol: 'https:', host: 'demo.example.com' })).toBe(
    'wss://demo.example.com/ws'
  );
});

test('explicit gateway websocket url overrides inferred origin', () => {
  process.env.NEXT_PUBLIC_GATEWAY_WS_URL = 'wss://gateway.example.com/custom-ws';

  expect(resolveGatewayWebSocketUrl({ protocol: 'http:', host: 'demo.example.com:3000' })).toBe(
    'wss://gateway.example.com/custom-ws'
  );
});
