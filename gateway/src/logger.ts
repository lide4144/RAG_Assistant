export type LogLevel = 'info' | 'warn' | 'error';

export function log(level: LogLevel, message: string, fields: Record<string, unknown> = {}): void {
  const payload = {
    ts: new Date().toISOString(),
    level,
    message,
    ...fields
  };
  const line = JSON.stringify(payload);
  if (level === 'error') {
    console.error(line);
    return;
  }
  if (level === 'warn') {
    console.warn(line);
    return;
  }
  console.log(line);
}
