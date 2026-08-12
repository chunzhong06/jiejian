import { request } from './http'

export type SystemStatus = {
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unknown'
  browser: 'available' | 'unavailable' | 'unknown'
}

export const systemApi = {
  status: () => request<SystemStatus>('/api/v1/system/status'),
}
