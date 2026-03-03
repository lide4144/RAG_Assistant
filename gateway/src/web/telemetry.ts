export interface WebProviderTelemetryState {
  providerConfigured: 'mock' | 'duckduckgo';
  providerUsed: 'mock' | 'duckduckgo';
  webProviderOk: boolean;
  isMockFallback: boolean;
  lastWebProviderError?: string;
  lastFallbackReason?: string;
  checkedAt: string;
}

let state: WebProviderTelemetryState = {
  providerConfigured: 'mock',
  providerUsed: 'mock',
  webProviderOk: true,
  isMockFallback: false,
  checkedAt: new Date().toISOString()
};

export function setConfiguredProvider(provider: 'mock' | 'duckduckgo'): void {
  state = {
    ...state,
    providerConfigured: provider,
    providerUsed: provider,
    checkedAt: new Date().toISOString()
  };
}

export function recordWebProviderSuccess(providerUsed: 'mock' | 'duckduckgo'): void {
  state = {
    ...state,
    providerUsed,
    webProviderOk: true,
    isMockFallback: false,
    lastWebProviderError: undefined,
    lastFallbackReason: undefined,
    checkedAt: new Date().toISOString()
  };
}

export function recordWebProviderFallback(reason: string): void {
  state = {
    ...state,
    providerUsed: 'mock',
    webProviderOk: false,
    isMockFallback: true,
    lastWebProviderError: reason,
    lastFallbackReason: reason,
    checkedAt: new Date().toISOString()
  };
}

export function recordWebProviderFailure(reason: string): void {
  state = {
    ...state,
    providerUsed: state.providerConfigured,
    webProviderOk: false,
    isMockFallback: false,
    lastWebProviderError: reason,
    checkedAt: new Date().toISOString()
  };
}

export function getWebProviderTelemetryState(): WebProviderTelemetryState {
  return { ...state };
}
