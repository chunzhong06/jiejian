// 补充材料独立于正式证据和执行准备；写入携带稳定请求身份，修订追加保存。
import { request } from './http'
export type SupplementalDocument = { schema_version: '1'; project_id: string; action_id: string; action_revision: number; title: string; source_label: string; claimed_resource_label: string | null; records: Array<{ recorded_at_us: number; resource_label: string; event_label: string }> }
export type MaterialPreview = { project_id: string; action_id: string; document: SupplementalDocument; fingerprint: string; record_count: number; association_status: 'USER_DECLARED' | 'UNCONFIRMED'; usage: 'SUPPLEMENTAL_ONLY' }
export type SupplementalMaterial = Omit<SupplementalDocument, 'schema_version'> & { material_id: string; revision: number; record_count: number; received_at_us: number; updated_at_us: number; association_status: 'USER_DECLARED' | 'UNCONFIRMED'; usage: 'SUPPLEMENTAL_ONLY'; withdrawn: boolean; fingerprint: string }
const base = (project: string, action: string) => `/api/projects/${encodeURIComponent(project)}/actions/${encodeURIComponent(action)}/supplemental-materials`
export const supplementalMaterialsApi = {
  list: (project: string, action: string) => request<{ project_id: string; action_id: string; items: SupplementalMaterial[]; has_more: boolean }>(base(project, action)),
  preview: (project: string, action: string, document: unknown) => request<MaterialPreview>(`${base(project, action)}/preview`, { method: 'POST', body: JSON.stringify({ document }) }),
  create: (project: string, action: string, document: SupplementalDocument, fingerprint: string, requestId: string) => request<SupplementalMaterial>(base(project, action), { method: 'POST', body: JSON.stringify({ document, expected_fingerprint: fingerprint, request_id: requestId }) }),
  revisions: (project: string, action: string, material: string, beforeRevision?: number) => request<{ project_id: string; action_id: string; items: SupplementalMaterial[]; has_more: boolean }>(`${base(project, action)}/${encodeURIComponent(material)}/revisions${beforeRevision ? `?before_revision=${beforeRevision}` : ''}`),
  revise: (project: string, action: string, material: string, body: { expected_revision: number; title: string; source_label: string; claimed_resource_label: string | null; request_id: string }) => request<SupplementalMaterial>(`${base(project, action)}/${encodeURIComponent(material)}/revisions`, { method: 'POST', body: JSON.stringify(body) }),
  withdraw: (project: string, action: string, material: string, revision: number, requestId: string) => request<SupplementalMaterial>(`${base(project, action)}/${encodeURIComponent(material)}/withdraw`, { method: 'POST', body: JSON.stringify({ expected_revision: revision, request_id: requestId }) }),
}
