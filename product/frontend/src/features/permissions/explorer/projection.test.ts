import { describe, expect, it } from 'vitest'
import type { PermissionContractDto } from '../../../api/contracts'
import { buildFocusedRelationshipGraph, buildGlobalRelationshipGraph, buildPermissionMatrix } from './projection'

const contract: PermissionContractDto = {
  schema_version: '1',
  contract_id: 'demo-contract',
  version: 1,
  subjects: [
    { subject_id: 'attacker', roles: ['user'] },
    { subject_id: 'owner', roles: ['user'] },
    { subject_id: 'peer', roles: ['guest'] },
  ],
  actions: [{ action_id: 'modify' }],
  resources: [
    { resource_id: 'attacker-resource', resource_type: 'document' },
    { resource_id: 'owner-resource', resource_type: 'document' },
  ],
  relations: [
    { relation_id: 'attacker-owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'attacker' }, target: { endpoint_type: 'resource', endpoint_id: 'attacker-resource' } },
    { relation_id: 'owner-owns', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'owner' }, target: { endpoint_type: 'resource', endpoint_id: 'owner-resource' } },
    { relation_id: 'same-tenant', relation: 'SAME_TENANT', source: { endpoint_type: 'subject', endpoint_id: 'attacker' }, target: { endpoint_type: 'subject', endpoint_id: 'owner' } },
  ],
  rules: [{ rule_id: 'unauthorized-modify', subject_id: 'attacker', action_id: 'modify', resource_id: 'owner-resource', expectation: 'DENY', severity: 'critical' }],
  batch_rules: [],
}

describe('permission explorer projections', () => {
  it('builds matrix cells without mutating the contract', () => {
    const before = JSON.stringify(contract)
    const matrix = buildPermissionMatrix(contract)
    const attacker = matrix.rows.find((row) => row.subject.subject_id === 'attacker')
    expect(attacker?.cells['modify:owner-resource'].state).toBe('DENY')
    expect(JSON.stringify(contract)).toBe(before)
  })

  it('keeps global graph to identities, resources and business relations', () => {
    const graph = buildGlobalRelationshipGraph(contract)
    expect(graph.nodes.map((node) => node.id)).toEqual([
      'subject:attacker', 'subject:owner', 'subject:peer',
      'resource:attacker-resource', 'resource:owner-resource',
    ])
    expect(graph.nodes.some((node) => node.id.startsWith('role:'))).toBe(false)
    expect(graph.edges.map((edge) => edge.label)).toEqual(expect.arrayContaining(['拥有', '同一租户']))
    expect(graph.edges.some((edge) => edge.kind === 'permission' || edge.label.includes('修改'))).toBe(false)
  })

  it('filters focused identity context and only then adds its permission edge', () => {
    const focused = buildFocusedRelationshipGraph(contract, 'attacker')
    expect(focused.nodes.some((node) => node.id === 'subject:peer')).toBe(false)
    expect(focused.nodes.some((node) => node.id === 'resource:owner-resource')).toBe(true)
    expect(focused.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'subject:attacker', target: 'resource:owner-resource', kind: 'permission', expectation: 'DENY' }),
    ]))

    const restored = buildGlobalRelationshipGraph(contract)
    expect(restored.nodes.some((node) => node.id === 'subject:peer')).toBe(true)
    expect(restored.edges.some((edge) => edge.kind === 'permission')).toBe(false)
  })

  it('keeps multiple resources in one identity lane without overlapping', () => {
    const graph = buildGlobalRelationshipGraph({
      ...contract,
      resources: [...contract.resources!, { resource_id: 'attacker-archive', resource_type: 'document' }],
      relations: [...contract.relations!, { relation_id: 'attacker-owns-archive', relation: 'OWNS', source: { endpoint_type: 'subject', endpoint_id: 'attacker' }, target: { endpoint_type: 'resource', endpoint_id: 'attacker-archive' } }],
    })
    const attackerResources = graph.nodes.filter((node) => node.id === 'resource:attacker-resource' || node.id === 'resource:attacker-archive')
    expect(new Set(attackerResources.map((node) => node.position.y)).size).toBe(2)
  })
})
