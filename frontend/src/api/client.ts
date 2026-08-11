export type ApiEnvelope<T> = { schema_version: '1'; data: T }

export class ApiError extends Error {
  code: string
  traceId?: string
  constructor(code: string, message: string, traceId?: string) {
    super(message)
    this.code = code
    this.traceId = traceId
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? 'API_ERROR', body.error?.message ?? '请求失败', body.trace_id)
  }
  return (body as ApiEnvelope<T>).data
}

export const api = {
  projects: () => request<Record<string, unknown>[]>('/api/v1/projects'),
  registerProject: (path: string, revalidate = false) =>
    request<Record<string, unknown>>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', path, revalidate }),
    }),
  project: (id: string) => request<Record<string, unknown>>(`/api/v1/projects/${id}`),
  revalidate: (id: string) => request<Record<string, unknown>>(`/api/v1/projects/${id}/revalidate`, { method: 'POST' }),
  contracts: (id: string) => request<Record<string, unknown>[]>(`/api/v1/projects/${id}/contracts`),
  activateContract: (id: string, path: string) =>
    request<Record<string, unknown>>(`/api/v1/projects/${id}/contracts/activate`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', path }),
    }),
  createRecording: (id: string, identities: string[], durationSeconds: number) =>
    request<Record<string, unknown>>(`/api/v1/projects/${id}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        identities,
        duration_seconds: durationSeconds,
        headless: true,
        idempotency_key: `gui-recording-${crypto.randomUUID()}`,
      }),
    }),
  recordings: (id: string) => request<Record<string, unknown>[]>(`/api/v1/projects/${id}/recordings`),
  recording: (id: string) => request<Record<string, unknown>>(`/api/v1/recordings/${id}`),
  reviewRecording: (
    id: string,
    command: Record<string, unknown>,
    bindings?: Record<string, Record<string, string>>,
  ) =>
    request<Record<string, unknown>>(`/api/v1/recordings/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', command, bindings }),
    }),
  finalizeRecording: (id: string) => request<Record<string, unknown>>(`/api/v1/recordings/${id}/finalize`, { method: 'POST' }),
  runs: (id: string) => request<Record<string, unknown>[]>(`/api/v1/projects/${id}/runs`),
  run: (id: string) => request<Record<string, unknown>>(`/api/v1/runs/${id}`),
  createRun: (id: string) =>
    request<Record<string, unknown>>(`/api/v1/projects/${id}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        idempotency_key: `gui-${crypto.randomUUID()}`,
      }),
    }),
  cancel: (jobId: string) => request<Record<string, unknown>>(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' }),
  report: (runId: string) => request<Record<string, unknown>>(`/api/v1/runs/${runId}/report`),
  findings: (runId: string) => request<Record<string, unknown>[]>(`/api/v1/runs/${runId}/findings`),
  evidence: (runId: string) => request<Record<string, unknown>[]>(`/api/v1/runs/${runId}/evidence`),
  evidenceDetail: (runId: string, evidenceId: string) => request<Record<string, unknown>>(`/api/v1/runs/${runId}/evidence/${evidenceId}`),
}
