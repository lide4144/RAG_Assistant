import type { Express, Request, Response } from 'express';
import { healthcheckKernel } from '../adapters/pythonKernelClient.js';
import { checkWebProviderHealth } from '../web/providers.js';
import { getWebProviderTelemetryState } from '../web/telemetry.js';

export function registerHealthRoute(app: Express): void {
  app.get('/health', async (_req: Request, res: Response) => {
    const kernelHealthy = await healthcheckKernel();
    res.status(200).json({
      status: 'ok',
      service: 'gateway',
      dependencies: {
        kernel: kernelHealthy ? 'up' : 'down'
      },
      now: new Date().toISOString()
    });
  });

  app.get('/health/deps', async (_req: Request, res: Response) => {
    const [kernelOk, webCheck] = await Promise.all([healthcheckKernel(), checkWebProviderHealth()]);
    const telemetry = getWebProviderTelemetryState();

    res.status(200).json({
      status: kernelOk && webCheck.ok ? 'ok' : 'degraded',
      kernel_ok: kernelOk,
      web_provider_ok: webCheck.ok,
      provider_configured: telemetry.providerConfigured,
      provider_used: telemetry.providerUsed,
      is_mock_fallback: telemetry.isMockFallback,
      last_web_provider_error: webCheck.error ?? telemetry.lastWebProviderError ?? null,
      last_fallback_reason: telemetry.lastFallbackReason ?? null,
      checked_at: new Date().toISOString()
    });
  });
}
