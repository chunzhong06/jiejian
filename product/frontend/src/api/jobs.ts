// 录制任务的取消与事件合同；当前检查状态由 currentChecks 客户端负责。
import { request } from './http'

export type JobEventDto = {
  schema_version?: '1'
  sequence: number
  event_type?: string
  state?: string
}

export type CancelJobDto = { schema_version?: '1'; job_id: string; state: string }

export const jobsApi = {
  cancel: (jobId: string) => request<CancelJobDto>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
}
