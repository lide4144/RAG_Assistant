export const KernelErrorCode = {
  INVALID_REQUEST: 'KERNEL_INVALID_REQUEST',
  TIMEOUT: 'KERNEL_TIMEOUT',
  NETWORK: 'KERNEL_NETWORK',
  BAD_RESPONSE: 'KERNEL_BAD_RESPONSE',
  UNKNOWN: 'KERNEL_UNKNOWN'
} as const;

export type KernelErrorCode = (typeof KernelErrorCode)[keyof typeof KernelErrorCode];

export class KernelClientError extends Error {
  constructor(
    public readonly code: KernelErrorCode,
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = 'KernelClientError';
  }
}
