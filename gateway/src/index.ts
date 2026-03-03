import express, { type Request, type Response, type NextFunction } from 'express';
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { config } from './config.js';
import { log } from './logger.js';
import { KernelClientError } from './errors.js';
import { registerHealthRoute } from './routes/health.js';
import { createChatService } from './chatService.js';

const app = express();
app.use(express.json({ limit: '1mb' }));
const resTraceMap = new WeakMap<Request, string>();

app.use((req: Request, _res: Response, next: NextFunction) => {
  const traceId = req.header('x-trace-id') ?? crypto.randomUUID();
  resTraceMap.set(req, traceId);
  log('info', 'http_request_started', {
    method: req.method,
    path: req.path,
    trace_id: traceId
  });
  next();
});

registerHealthRoute(app);

app.use((err: unknown, req: Request, res: Response, _next: NextFunction) => {
  const traceId = resTraceMap.get(req) ?? 'unknown';
  log('error', 'unhandled_error', {
    trace_id: traceId,
    error: err instanceof Error ? err.message : 'unknown error'
  });
  res.status(500).json({ error: 'INTERNAL_GATEWAY_ERROR', traceId });
});

const server = createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });
const handleRawClientEvent = createChatService();

wss.on('connection', (ws, request) => {
  const traceId = request.headers['x-trace-id']?.toString() ?? crypto.randomUUID();
  log('info', 'ws_connected', { trace_id: traceId });

  const sendEvent = (event: unknown) => {
    if (ws.readyState === 1) {
      ws.send(JSON.stringify(event));
    }
  };

  ws.on('message', async (raw) => {
    const requestTraceId = crypto.randomUUID();

    try {
      await handleRawClientEvent(raw.toString(), sendEvent);
    } catch (error) {
      const eventCode = error instanceof KernelClientError ? error.code : 'GATEWAY_PROTOCOL_ERROR';
      sendEvent({
        type: 'error',
        traceId: requestTraceId,
        code: eventCode,
        message: error instanceof Error ? error.message : 'Unknown websocket error'
      });
      log('warn', 'ws_request_failed', {
        trace_id: requestTraceId,
        code: eventCode,
        error: error instanceof Error ? error.message : 'unknown'
      });
    }
  });

  ws.on('close', () => {
    log('info', 'ws_closed', { trace_id: traceId });
  });
});

server.listen(config.port, config.host, () => {
  log('info', 'gateway_started', {
    host: config.host,
    port: config.port,
    kernel_base_url: config.kernelBaseUrl,
    web_provider: config.webProvider,
    web_provider_strict: config.webProviderStrict
  });
});
