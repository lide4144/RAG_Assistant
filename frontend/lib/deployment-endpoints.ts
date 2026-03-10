type LocationLike = Pick<Location, 'host' | 'protocol'>;

const normalizeHttpBase = (raw: string): string => raw.trim().replace(/\/+$/, '');

const ensureLeadingSlash = (path: string): string => (path.startsWith('/') ? path : `/${path}`);

export function resolveKernelBaseUrl(): string {
  return normalizeHttpBase(process.env.NEXT_PUBLIC_KERNEL_BASE_URL ?? '');
}

export function resolveAdminUrl(path: string): string {
  const normalizedPath = ensureLeadingSlash(path);
  const kernelBaseUrl = resolveKernelBaseUrl();
  return kernelBaseUrl ? `${kernelBaseUrl}${normalizedPath}` : normalizedPath;
}

export function resolveGatewayWebSocketUrl(locationLike?: LocationLike): string {
  const explicitUrl = (process.env.NEXT_PUBLIC_GATEWAY_WS_URL ?? '').trim();
  if (explicitUrl) {
    return explicitUrl;
  }

  const currentLocation = locationLike ?? (typeof window !== 'undefined' ? window.location : undefined);
  if (!currentLocation) {
    return '';
  }

  const protocol = currentLocation.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${currentLocation.host}/ws`;
}
