/* 权限浏览只读模型；由纯 projection 生成，组件不直接解释协议对象。 */

import type { PermissionResourceDto, PermissionRuleDto, PermissionSubjectDto } from '../../../api/contracts'

export type PermissionCellState = 'ALLOW' | 'DENY' | 'UNDECLARED' | 'CONFLICT'

export type ExpandedPermissionRule = PermissionRuleDto & {
  batch_rule_id?: string
  atomic?: boolean
}

export type PermissionMatrixCell = {
  actionId: string
  resource: PermissionResourceDto
  rules: ExpandedPermissionRule[]
  state: PermissionCellState
}

export type PermissionMatrixRow = {
  key: string
  subject: PermissionSubjectDto
  cells: Record<string, PermissionMatrixCell>
}

export type PermissionMatrixModel = {
  subjects: PermissionSubjectDto[]
  actions: string[]
  resources: PermissionResourceDto[]
  roles: string[]
  rows: PermissionMatrixRow[]
}

export type RelationshipNode = {
  id: string
  kind: 'identity' | 'resource'
  rawId: string
  label: string
  secondary?: string
  roles?: string[]
  position: { x: number; y: number }
}

export type RelationshipEdge = {
  id: string
  source: string
  target: string
  kind: 'relation' | 'ownership' | 'permission'
  label: string
  expectation?: string
}

export type RelationshipGraphModel = {
  mode: 'global' | 'focused'
  focusSubjectId?: string
  nodes: RelationshipNode[]
  edges: RelationshipEdge[]
}
