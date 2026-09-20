// 源码对应只读客户端；记录内容与当前 Git 上下文不代表运行目标部署身份。
import { request } from './http'
export type SourceIdentity = {
  project_id: string; run_id: string | null; change_id: string | null
  comparison: 'SAME' | 'CHANGED' | 'NO_BASELINE' | 'UNAVAILABLE'
  recorded: { fingerprint: string; snapshot_id: string | null; file_count: number | null; git_status: 'NOT_RECORDED' } | null
  current_fingerprint: string | null
  current_git: { status: 'AVAILABLE' | 'UNBORN' | 'NOT_A_REPOSITORY' | 'UNAVAILABLE'; head: string | null; has_local_changes: boolean | null }
  observed_at_us: number; target_version: 'NOT_INDEPENDENTLY_IDENTIFIED'
}
export const sourceIdentityApi = {
  read: (project: string, kind: 'runs' | 'source-changes', id: string) => request<SourceIdentity>(`/api/projects/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(id)}/source-identity`),
}
