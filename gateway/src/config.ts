export interface GatewayConfig {
  host: string;
  port: number;
  kernelBaseUrl: string;
  requestTimeoutMs: number;
  webProvider: 'mock' | 'duckduckgo';
  webProviderStrict: boolean;
  webTopK: number;
  streamChunkSize: number;
  streamChunkDelayMs: number;
}

function parseWebProvider(raw: string | undefined): 'mock' | 'duckduckgo' {
  if (raw === 'duckduckgo') {
    return 'duckduckgo';
  }
  return 'mock';
}

export const config: GatewayConfig = {
  host: process.env.GATEWAY_HOST ?? '0.0.0.0',
  port: Number(process.env.GATEWAY_PORT ?? '8080'),
  kernelBaseUrl: process.env.KERNEL_BASE_URL ?? 'http://127.0.0.1:8000',
  requestTimeoutMs: Number(process.env.KERNEL_TIMEOUT_MS ?? '30000'),
  webProvider: parseWebProvider(process.env.WEB_PROVIDER),
  webProviderStrict: process.env.WEB_PROVIDER_STRICT === 'true',
  webTopK: Number(process.env.WEB_TOP_K ?? '5'),
  streamChunkSize: Number(process.env.STREAM_CHUNK_SIZE ?? '36'),
  streamChunkDelayMs: Number(process.env.STREAM_CHUNK_DELAY_MS ?? '12')
};
