/* 首次使用 API：只提供目录选择与受限只读识别，不保存快速检查会话。 */

import { request } from '../../../shared/api/http'

export type DiscoveryCandidate = {
  label: string
  command: string
  source: string
  confirmation_required: true
  executed: false
  safety_note: string
}

export type DiscoveryHint = {
  detail: string
  source: string
  confirmation_required: true
}

export type DiscoveryResult = {
  detected_types: string[]
  start_candidates: DiscoveryCandidate[]
  config_hints: DiscoveryHint[]
  interface_hints: DiscoveryHint[]
  auth_hints: DiscoveryHint[]
  missing_items: Array<{ key: string; label: string; state: string; reason: string; confirmation_required: true }>
  warnings: Array<{ code: string; message: string }>
}

export const onboardingApi = {
  selectFolder: (signal?: AbortSignal) => request<{ status: 'selected' | 'cancelled' | 'unavailable'; path?: string; message?: string }>('/api/onboarding/select-folder', { method: 'POST', signal }),
  inspect: (path: string) => request<DiscoveryResult>('/api/onboarding/inspect', { method: 'POST', body: JSON.stringify({ schema_version: '1', path }) }),
}

/** 取消选择保留原输入；不可用时由当前工作面说明手工路径回退。 */
export async function selectFolderPath():Promise<string|null>{
  const value=await onboardingApi.selectFolder()
  if(value.status==='selected'&&value.path)return value.path
  if(value.status==='unavailable')throw new Error(value.message??'系统目录选择暂时不可用，请粘贴完整路径。')
  return null
}
