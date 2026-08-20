/* PermissionContract 纯投影：统一规则展开、矩阵建模和确定性身份 lane 图布局。 */

import type {
  PermissionContractDto,
  PermissionEndpointDto,
  PermissionRelationDto,
  PermissionResourceDto,
  PermissionRuleDto,
  PermissionSubjectDto,
} from '../../../api/contracts'
import { productTermLabel } from '../../../app/presentation'
import type {
  ExpandedPermissionRule,
  PermissionCellState,
  PermissionMatrixModel,
  RelationshipEdge,
  RelationshipGraphModel,
  RelationshipNode,
} from './types'

const IDENTITY_X = 120
const RESOURCE_X = 650
const LANE_TOP = 70
const LANE_GAP = 180
const RESOURCE_GAP = 132

function identityNodeId(id: string) { return `subject:${id}` }
function resourceNodeId(id: string) { return `resource:${id}` }

function endpointNodeId(endpoint: PermissionEndpointDto) {
  const kind = endpoint.endpoint_type.toLowerCase()
  if (kind === 'subject' || kind === 'identity') return identityNodeId(endpoint.endpoint_id)
  if (kind === 'resource') return resourceNodeId(endpoint.endpoint_id)
  return null
}

export function expandPermissionRules(contract: PermissionContractDto): ExpandedPermissionRule[] {
  const ordinary = (contract.rules ?? []).map((rule) => ({ ...rule }))
  const batch = (contract.batch_rules ?? []).flatMap((rule) =>
    (rule.resource_expectations ?? []).map((expectation) => ({
      ...rule,
      resource_id: expectation.resource_id,
      expectation: expectation.expectation,
      relation_path: expectation.relation_path ?? [],
      batch_rule_id: rule.rule_id,
      atomic: Boolean(rule.atomic),
    })),
  )
  return [...ordinary, ...batch]
}

function cellState(rules: ExpandedPermissionRule[]): PermissionCellState {
  if (rules.length === 0) return 'UNDECLARED'
  const expectations = new Set(rules.map((rule) => rule.expectation))
  if (expectations.size !== 1) return 'CONFLICT'
  return expectations.has('ALLOW') ? 'ALLOW' : expectations.has('DENY') ? 'DENY' : 'CONFLICT'
}

export function buildPermissionMatrix(contract: PermissionContractDto): PermissionMatrixModel {
  const rules = expandPermissionRules(contract)
  const subjects = [...(contract.subjects ?? [])].sort((left, right) => left.subject_id.localeCompare(right.subject_id))
  const actions = [...new Set([...(contract.actions ?? []).map((item) => item.action_id), ...rules.map((rule) => rule.action_id)])].sort()
  const resourceMap = new Map<string, PermissionResourceDto>((contract.resources ?? []).map((resource) => [resource.resource_id, resource]))
  for (const rule of rules) if (!resourceMap.has(rule.resource_id)) resourceMap.set(rule.resource_id, { resource_id: rule.resource_id })
  const resources = [...resourceMap.values()].sort((left, right) => left.resource_id.localeCompare(right.resource_id))
  const roles = [...new Set(subjects.flatMap((subject) => subject.roles ?? []))].sort()
  const rows = subjects.map((subject) => {
    const cells: PermissionMatrixModel['rows'][number]['cells'] = {}
    for (const actionId of actions) {
      for (const resource of resources) {
        const matches = rules.filter((rule) => rule.subject_id === subject.subject_id && rule.action_id === actionId && rule.resource_id === resource.resource_id)
        cells[`${actionId}:${resource.resource_id}`] = { actionId, resource, rules: matches, state: cellState(matches) }
      }
    }
    return { key: subject.subject_id, subject, cells }
  })
  return { subjects, actions, resources, roles, rows }
}

function relationKind(relation: PermissionRelationDto): RelationshipEdge['kind'] {
  return relation.relation.toUpperCase() === 'OWNS' ? 'ownership' : 'relation'
}

function relationshipEdges(relations: PermissionRelationDto[], allowedNodes: Set<string>): RelationshipEdge[] {
  return relations.flatMap((relation, index) => {
    const source = endpointNodeId(relation.source)
    const target = endpointNodeId(relation.target)
    if (!source || !target || !allowedNodes.has(source) || !allowedNodes.has(target)) return []
    return [{
      id: `relation-${relation.relation_id ?? index}-${source}-${target}`,
      source,
      target,
      kind: relationKind(relation),
      label: productTermLabel('relation', relation.relation, false),
    }]
  })
}

function orderSubjects(subjects: PermissionSubjectDto[], relations: PermissionRelationDto[], focus?: string) {
  const byId = new Map(subjects.map((subject) => [subject.subject_id, subject]))
  const ordered: PermissionSubjectDto[] = []
  const visited = new Set<string>()
  const visit = (id: string) => {
    if (visited.has(id) || !byId.has(id)) return
    visited.add(id)
    ordered.push(byId.get(id)!)
    const neighbours = relations.flatMap((relation) => {
      const source = endpointNodeId(relation.source)
      const target = endpointNodeId(relation.target)
      if (source === identityNodeId(id) && target?.startsWith('subject:')) return [target.slice('subject:'.length)]
      if (target === identityNodeId(id) && source?.startsWith('subject:')) return [source.slice('subject:'.length)]
      return []
    }).sort()
    neighbours.forEach(visit)
  }
  if (focus) visit(focus)
  const remaining = [...subjects].sort((left, right) => left.subject_id.localeCompare(right.subject_id))
  remaining.forEach((subject) => visit(subject.subject_id))
  return ordered
}

function buildNodes(subjects: PermissionSubjectDto[], resources: PermissionResourceDto[], relations: PermissionRelationDto[], rules: ExpandedPermissionRule[], focus?: string): RelationshipNode[] {
  const orderedSubjects = orderSubjects(subjects, relations, focus)
  const ownedBy = new Map<string, string>()
  for (const relation of relations) {
    if (relationKind(relation) !== 'ownership') continue
    const source = endpointNodeId(relation.source)
    const target = endpointNodeId(relation.target)
    if (source?.startsWith('subject:') && target?.startsWith('resource:')) ownedBy.set(target.slice('resource:'.length), source.slice('subject:'.length))
  }
  // 聚焦身份的规则资源如果没有显式 Owner，仍放在该身份 lane，避免孤立到画布底部。
  if (focus) for (const rule of rules) if (rule.subject_id === focus && !ownedBy.has(rule.resource_id)) ownedBy.set(rule.resource_id, focus)
  const orderedResources = [...resources].sort((left, right) => left.resource_id.localeCompare(right.resource_id))
  const resourcesByIdentity = new Map(orderedSubjects.map((subject) => [subject.subject_id, orderedResources.filter((resource) => ownedBy.get(resource.resource_id) === subject.subject_id)]))
  const laneByIdentity = new Map<string, number>()
  const resourceY = new Map<string, number>()
  let nextLaneTop = LANE_TOP
  for (const subject of orderedSubjects) {
    const laneResources = resourcesByIdentity.get(subject.subject_id) ?? []
    laneByIdentity.set(subject.subject_id, nextLaneTop + Math.max(0, laneResources.length - 1) * RESOURCE_GAP / 2)
    laneResources.forEach((resource, index) => resourceY.set(resource.resource_id, nextLaneTop + index * RESOURCE_GAP))
    nextLaneTop += Math.max(LANE_GAP, laneResources.length * RESOURCE_GAP)
  }
  orderedResources.filter((resource) => !resourceY.has(resource.resource_id)).forEach((resource, index) => resourceY.set(resource.resource_id, nextLaneTop + index * RESOURCE_GAP))
  const nodes: RelationshipNode[] = orderedSubjects.map((subject) => ({
    id: identityNodeId(subject.subject_id),
    kind: 'identity',
    rawId: subject.subject_id,
    label: productTermLabel('identity', subject.subject_id, false),
    roles: (subject.roles ?? []).map((role) => productTermLabel('role', role, false)),
    position: { x: IDENTITY_X, y: laneByIdentity.get(subject.subject_id)! },
  }))
  orderedResources.forEach((resource) => {
    nodes.push({
      id: resourceNodeId(resource.resource_id),
      kind: 'resource',
      rawId: resource.resource_id,
      label: productTermLabel('resource', resource.resource_id, false),
      secondary: productTermLabel('resourceType', resource.resource_type, false),
      position: { x: RESOURCE_X, y: resourceY.get(resource.resource_id)! },
    })
  })
  return nodes
}

function buildGraph(contract: PermissionContractDto, focus?: string): RelationshipGraphModel {
  const allSubjects = contract.subjects ?? []
  const allResources = contract.resources ?? []
  const relations = contract.relations ?? []
  const rules = expandPermissionRules(contract)
  let subjects = [...allSubjects]
  let resources = [...allResources]

  if (focus) {
    const identities = new Set([focus])
    const resourceIds = new Set<string>()
    for (const relation of relations) {
      const source = endpointNodeId(relation.source)
      const target = endpointNodeId(relation.target)
      if (source === identityNodeId(focus) || target === identityNodeId(focus)) {
        if (source?.startsWith('subject:')) identities.add(source.slice('subject:'.length))
        if (target?.startsWith('subject:')) identities.add(target.slice('subject:'.length))
        if (source?.startsWith('resource:')) resourceIds.add(source.slice('resource:'.length))
        if (target?.startsWith('resource:')) resourceIds.add(target.slice('resource:'.length))
      }
    }
    // 直接相关身份所拥有的资源提供一跳业务上下文，但不继续扩散到其他身份。
    for (const relation of relations) {
      const source = endpointNodeId(relation.source)
      const target = endpointNodeId(relation.target)
      if (source?.startsWith('subject:') && identities.has(source.slice('subject:'.length)) && target?.startsWith('resource:')) resourceIds.add(target.slice('resource:'.length))
      if (target?.startsWith('subject:') && identities.has(target.slice('subject:'.length)) && source?.startsWith('resource:')) resourceIds.add(source.slice('resource:'.length))
    }
    for (const rule of rules) if (rule.subject_id === focus) resourceIds.add(rule.resource_id)
    subjects = allSubjects.filter((subject) => identities.has(subject.subject_id))
    resources = allResources.filter((resource) => resourceIds.has(resource.resource_id))
    for (const resourceId of resourceIds) if (!resources.some((resource) => resource.resource_id === resourceId)) resources.push({ resource_id: resourceId })
  }

  const nodes = buildNodes(subjects, resources, relations, rules, focus)
  const allowedNodes = new Set(nodes.map((node) => node.id))
  const edges = relationshipEdges(relations, allowedNodes)
  if (focus) {
    rules.filter((rule) => rule.subject_id === focus && allowedNodes.has(resourceNodeId(rule.resource_id))).forEach((rule, index) => {
      edges.push({
        id: `permission-${rule.rule_id ?? index}-${rule.resource_id}`,
        source: identityNodeId(focus),
        target: resourceNodeId(rule.resource_id),
        kind: 'permission',
        label: `${productTermLabel('action', rule.action_id, false)} · ${rule.expectation === 'ALLOW' ? '允许' : rule.expectation === 'DENY' ? '拒绝' : rule.expectation}`,
        expectation: rule.expectation,
      })
    })
  }
  return { mode: focus ? 'focused' : 'global', focusSubjectId: focus, nodes, edges }
}

export function buildGlobalRelationshipGraph(contract: PermissionContractDto) {
  return buildGraph(contract)
}

export function buildFocusedRelationshipGraph(contract: PermissionContractDto, subjectId: string) {
  return buildGraph(contract, subjectId)
}
