// GUI与MCP共用后端建议；本地不决定主任务、材料可用性或权限结论。
export type PreparationNextAction = {
  kind: string; title: string; reason: string; handler: 'USER' | 'AGENT' | 'EITHER' | 'SYSTEM'; gui_url: string
  mcp_tool: string | null; required_level: 'READ' | 'PREPARE' | 'EXECUTE' | null
  action_id: string | null; action_revision: number | null; effect_id: string | null
  source_id: string | null; source_revision: number | null; preflight_id: string | null; task_id: string | null
}
export type PreparationMaterialAdvice = {
  action_id: string; action_revision: number; kind: 'identity' | 'execution' | 'resource' | 'evidence' | 'recovery'
  member_id: string | null; label: string; status: 'SATISFIED' | 'NEEDS_USER' | 'STALE' | 'BLOCKED' | 'NOT_REQUIRED'
  reason: string; reason_codes: string[]; gui_url: string
}
export type PreparationGuidance = {
  project_id: string; basis_id: string; state: 'CURRENT' | 'NEEDS_REFRESH'; next_action: PreparationNextAction | null
  materials: PreparationMaterialAdvice[]
  sources: Array<{source_id: string; revision: number; state: 'NEEDS_ACTION' | 'WAITING' | 'USABLE' | 'UNSUPPORTED'; next_action: PreparationNextAction | null}>
  note: string
}
