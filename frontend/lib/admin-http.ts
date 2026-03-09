export type AdminFetchSuccess<T> = {
  ok: true;
  status: number;
  data: T;
};

export type AdminFetchFailure = {
  ok: false;
  status: number;
  message: string;
  data?: unknown;
};

export type AdminFetchResult<T> = AdminFetchSuccess<T> | AdminFetchFailure;

const isJsonContentType = (contentType: string): boolean => {
  return contentType.toLowerCase().includes('application/json');
};

export async function fetchAdminJson<T>(url: string, init?: RequestInit): Promise<AdminFetchResult<T>> {
  const response = await fetch(url, init);
  const contentType = response.headers.get('content-type') ?? '';

  if (isJsonContentType(contentType)) {
    try {
      const payload = (await response.json()) as unknown;
      if (response.ok) {
        return { ok: true, status: response.status, data: payload as T };
      }
      return {
        ok: false,
        status: response.status,
        message: `HTTP ${response.status}`,
        data: payload
      };
    } catch {
      return {
        ok: false,
        status: response.status,
        message: `接口返回了非法 JSON（HTTP ${response.status}）。`
      };
    }
  }

  const bodyText = await response.text().catch(() => '');
  const snippet = bodyText.replace(/\s+/g, ' ').trim().slice(0, 120);
  return {
    ok: false,
    status: response.status,
    message: snippet
      ? `接口返回非 JSON 响应（HTTP ${response.status}）：${snippet}`
      : `接口返回非 JSON 响应（HTTP ${response.status}）。`
  };
}
