// 运行环境状态 API；仅暴露面向产品的可用性枚举。

import { request } from './http'

export type SystemStatus = {
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unknown'
  browser: 'available' | 'unavailable' | 'unknown'
}

export const systemApi = {
  status: () => request<SystemStatus>('/api/system/status'),
}
