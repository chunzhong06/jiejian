/* =============================================================================
 * PermissionContract DTO
 *
 * 定位
 *   权限关系只读投影使用的 Contract 类型边界
 *
 * 职责
 *   约束前端只读关系图需要的有限字段
 *
 * 调用链
 *   PermissionExplorer → Contract DTO
 * ============================================================================= */

export type PermissionSubjectDto = { subject_id: string; roles?: string[] }
export type PermissionActionDto = { action_id: string; effect_ids?: string[] }
export type SecurityEffectDto = {
  effect_id: string
  kind: string
  resource_type: string
  expected_state?: string | null
  protected_fields?: string[]
}
export type PermissionResourceDto = { resource_id: string; resource_type?: string }
export type PermissionEndpointDto = { endpoint_type: string; endpoint_id: string }
export type PermissionRelationDto = {
  relation_id?: string
  relation: string
  source: PermissionEndpointDto
  target: PermissionEndpointDto
}
export type PermissionRuleDto = {
  rule_id?: string
  id?: string
  subject_id: string
  action_id: string
  resource_id: string
  expectation: string
  severity?: string
  relation_path?: string[]
  context?: Record<string, unknown>
  required_observations?: string[]
}
export type PermissionBatchExpectationDto = {
  resource_id: string
  expectation: string
  relation_path?: string[]
}
export type PermissionBatchRuleDto = Omit<PermissionRuleDto, 'resource_id' | 'expectation'> & {
  atomic?: boolean
  resource_expectations?: PermissionBatchExpectationDto[]
}
export type PermissionContractDto = {
  schema_version?: '1'
  contract_id: string
  version: number
  status?: string
  subjects?: PermissionSubjectDto[]
  role_ids?: string[]
  effects?: SecurityEffectDto[]
  actions?: PermissionActionDto[]
  resources?: PermissionResourceDto[]
  relations?: PermissionRelationDto[]
  rules?: PermissionRuleDto[]
  batch_rules?: PermissionBatchRuleDto[]
}
