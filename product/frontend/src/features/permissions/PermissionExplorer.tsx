/* =============================================================================
 * PermissionContract 可视化
 *
 * 将只读契约投影为可筛选矩阵和可缩放关系图；不改变规则语义，也不参与漏洞判定。
 * ============================================================================= */

import { useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, Drawer, List, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { Background, Controls, MarkerType, MiniMap, Position, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { expectationLabel, severityLabel } from '../../app/presentation'

type Item = Record<string, any>
type MatrixRule = Item & { batch_rule_id?: string; atomic?: boolean }
type CellState = 'ALLOW' | 'DENY' | 'UNDECLARED' | 'CONFLICT'
type CellSelection = { subject: Item; actionId: string; resource: Item; rules: MatrixRule[]; state: CellState }

function text(value: unknown) { return String(value ?? '未提供') }
function contextSummary(value: unknown) {
  if (!value || typeof value !== 'object' || Object.keys(value as Item).length === 0) return '无附加条件'
  return Object.entries(value as Item).filter(([, item]) => item !== undefined && item !== null).map(([key, item]) => `${key}：${Array.isArray(item) ? item.join('、') : String(item)}`).join('；') || '无附加条件'
}
function expandedRules(contract: Item): MatrixRule[] {
  const ordinary = (Array.isArray(contract.rules) ? contract.rules : []).map((rule: Item) => ({ ...rule }))
  const batch = (Array.isArray(contract.batch_rules) ? contract.batch_rules : []).flatMap((rule: Item) =>
    (Array.isArray(rule.resource_expectations) ? rule.resource_expectations : []).map((expectation: Item) => ({
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
function cellState(rules: MatrixRule[]): CellState {
  if (rules.length === 0) return 'UNDECLARED'
  const expectations = new Set(rules.map((rule) => String(rule.expectation)))
  if (expectations.size !== 1) return 'CONFLICT'
  return expectations.has('ALLOW') ? 'ALLOW' : expectations.has('DENY') ? 'DENY' : 'CONFLICT'
}
function stateView(state: CellState) {
  if (state === 'ALLOW') return { label: '允许', color: 'green', explanation: '规则明确允许该身份对这个资源执行此动作。' }
  if (state === 'DENY') return { label: '拒绝', color: 'red', explanation: '规则明确拒绝该身份对这个资源执行此动作。' }
  if (state === 'CONFLICT') return { label: '规则冲突', color: 'gold', explanation: '同一单元格同时命中了不一致的期望，需要先消除冲突。' }
  return { label: '未声明', color: 'default', explanation: '当前契约没有声明这一身份、动作和资源组合。' }
}

function PermissionMatrix({ contract }: { contract: Item }) {
  const rules = useMemo(() => expandedRules(contract), [contract])
  const subjects = useMemo(() => [...(Array.isArray(contract.subjects) ? contract.subjects : [])].sort((left: Item, right: Item) => text(left.subject_id).localeCompare(text(right.subject_id))), [contract])
  const actionIds = useMemo(() => [...new Set([...(Array.isArray(contract.actions) ? contract.actions.map((item: Item) => text(item.action_id)) : []), ...rules.map((rule) => text(rule.action_id))])].sort(), [contract, rules])
  const resources = useMemo(() => {
    const values = new Map<string, Item>()
    for (const item of Array.isArray(contract.resources) ? contract.resources : []) values.set(text(item.resource_id), item)
    for (const rule of rules) if (!values.has(text(rule.resource_id))) values.set(text(rule.resource_id), { resource_id: rule.resource_id })
    return [...values.values()].sort((left, right) => text(left.resource_id).localeCompare(text(right.resource_id)))
  }, [contract, rules])
  const roles = useMemo(() => [...new Set(subjects.flatMap((subject) => Array.isArray(subject.roles) ? subject.roles.map(String) : []))].sort(), [subjects])
  const [subjectFilter, setSubjectFilter] = useState<string>()
  const [roleFilter, setRoleFilter] = useState<string>()
  const [actionFilter, setActionFilter] = useState<string>()
  const [resourceFilter, setResourceFilter] = useState<string>()
  const [selected, setSelected] = useState<CellSelection>()
  const visibleSubjects = subjects.filter((subject) => (!subjectFilter || text(subject.subject_id) === subjectFilter) && (!roleFilter || (subject.roles ?? []).map(String).includes(roleFilter)))
  const visibleActions = actionIds.filter((actionId) => !actionFilter || actionId === actionFilter)
  const visibleResources = resources.filter((resource) => !resourceFilter || text(resource.resource_id) === resourceFilter)
  const rows = visibleSubjects.map((subject) => ({ key: text(subject.subject_id), subject }))
  const columns: TableColumnsType<Item> = [
    {
      title: '身份 / 角色', key: 'subject', fixed: 'left', width: 220,
      render: (_, row) => <Space direction="vertical" size={0}><Typography.Text strong>{text(row.subject.subject_id)}</Typography.Text><Typography.Text type="secondary">{(row.subject.roles ?? []).map(String).join('、') || '未分配角色'}</Typography.Text></Space>,
    },
    ...visibleActions.map((actionId) => ({
      title: <Space direction="vertical" size={0}><Typography.Text strong>{actionId}</Typography.Text><Typography.Text type="secondary">动作</Typography.Text></Space>,
      key: `action:${actionId}`,
      children: visibleResources.map((resource) => {
        const resourceId = text(resource.resource_id)
        return {
          title: <Space direction="vertical" size={0}><Typography.Text>{resourceId}</Typography.Text><Typography.Text type="secondary">{text(resource.resource_type)}</Typography.Text></Space>,
          key: `${actionId}:${resourceId}`,
          width: 160,
          align: 'center' as const,
          render: (_: unknown, row: Item) => {
            const matches = rules.filter((rule) => text(rule.subject_id) === text(row.subject.subject_id) && text(rule.action_id) === actionId && text(rule.resource_id) === resourceId)
            const state = cellState(matches)
            const view = stateView(state)
            return <Button className="permission-cell" type="text" aria-label={`${text(row.subject.subject_id)} ${actionId} ${resourceId} ${view.label}`} onClick={() => setSelected({ subject: row.subject, actionId, resource, rules: matches, state })}><Tag color={view.color}>{view.label}</Tag></Button>
          },
        }
      }),
    })),
  ]
  return <Space direction="vertical" className="full-width" size="middle">
    <Space wrap>
      <Select allowClear aria-label="筛选身份" placeholder="筛选身份" value={subjectFilter} onChange={setSubjectFilter} style={{ minWidth: 160 }} options={subjects.map((item) => ({ value: text(item.subject_id), label: text(item.subject_id) }))} />
      <Select allowClear aria-label="筛选角色" placeholder="筛选角色" value={roleFilter} onChange={setRoleFilter} style={{ minWidth: 160 }} options={roles.map((item) => ({ value: item, label: item }))} />
      <Select allowClear aria-label="筛选动作" placeholder="筛选动作" value={actionFilter} onChange={setActionFilter} style={{ minWidth: 160 }} options={actionIds.map((item) => ({ value: item, label: item }))} />
      <Select allowClear aria-label="筛选资源" placeholder="筛选资源" value={resourceFilter} onChange={setResourceFilter} style={{ minWidth: 180 }} options={resources.map((item) => ({ value: text(item.resource_id), label: text(item.resource_id) }))} />
    </Space>
    <Space wrap aria-label="矩阵图例"><Typography.Text type="secondary">图例：</Typography.Text>{(['ALLOW', 'DENY', 'UNDECLARED', 'CONFLICT'] as CellState[]).map((state) => { const view = stateView(state); return <Tag key={state} color={view.color}>{view.label}</Tag> })}</Space>
    {(visibleActions.length === 0 || visibleResources.length === 0) && <Alert type="info" showIcon message="当前筛选范围没有可展示的动作与资源组合。" />}
    <Table<Item> className="permission-matrix" sticky columns={columns} dataSource={rows} pagination={false} size="small" scroll={{ x: 'max-content', y: 480 }} locale={{ emptyText: '当前筛选范围没有身份。' }} />
    <Drawer width={560} open={Boolean(selected)} onClose={() => setSelected(undefined)} title={selected ? `${text(selected.subject.subject_id)} · ${selected.actionId} · ${text(selected.resource.resource_id)}` : '权限详情'}>
      {selected && <Space direction="vertical" className="full-width" size="middle">
        <Alert showIcon type={selected.state === 'DENY' ? 'error' : selected.state === 'CONFLICT' ? 'warning' : selected.state === 'ALLOW' ? 'success' : 'info'} message={stateView(selected.state).label} description={stateView(selected.state).explanation} />
        <Descriptions size="small" column={1} bordered><Descriptions.Item label="谁">{text(selected.subject.subject_id)}（{(selected.subject.roles ?? []).map(String).join('、') || '未分配角色'}）</Descriptions.Item><Descriptions.Item label="做什么">{selected.actionId}</Descriptions.Item><Descriptions.Item label="对什么资源">{text(selected.resource.resource_id)}（{text(selected.resource.resource_type)}）</Descriptions.Item></Descriptions>
        <List size="small" header={<Typography.Text strong>命中的规则</Typography.Text>} dataSource={selected.rules} locale={{ emptyText: '没有命中规则' }} renderItem={(rule) => <List.Item><Space direction="vertical" className="full-width"><Space wrap><Tag color={String(rule.expectation) === 'ALLOW' ? 'green' : 'red'}>{expectationLabel(rule.expectation)}</Tag><Tag>{severityLabel(rule.severity)}</Tag></Space><Typography.Text>关系：{(rule.relation_path ?? []).join(' → ') || '无关系限制'}</Typography.Text><Typography.Text>条件：{contextSummary(rule.context)}</Typography.Text><Typography.Text>核验：{(rule.required_observations ?? []).join('、') || '未声明必需观察'}</Typography.Text><Collapse ghost items={[{ key: 'rule-tech', label: '高级：规则标识', children: <Typography.Text code>{text(rule.rule_id)}</Typography.Text> }]} /></Space></List.Item>} />
      </Space>}
    </Drawer>
  </Space>
}

function endpointId(value: Item | undefined) { return `${String(value?.endpoint_type ?? '').toLowerCase()}:${text(value?.endpoint_id)}` }
function nodeLabel(kind: string, id: string, detail?: string) {
  return <Space direction="vertical" size={0}><Typography.Text type="secondary">{kind}</Typography.Text><Typography.Text strong>{id}</Typography.Text>{detail && <Typography.Text type="secondary">{detail}</Typography.Text>}</Space>
}

function PermissionGraph({ contract }: { contract: Item }) {
  const [focus, setFocus] = useState<string>()
  const subjects = useMemo(() => [...(Array.isArray(contract.subjects) ? contract.subjects : [])].sort((left: Item, right: Item) => text(left.subject_id).localeCompare(text(right.subject_id))), [contract])
  const resources = useMemo(() => [...(Array.isArray(contract.resources) ? contract.resources : [])].sort((left: Item, right: Item) => text(left.resource_id).localeCompare(text(right.resource_id))), [contract])
  const roles = useMemo(() => [...new Set([...(Array.isArray(contract.role_ids) ? contract.role_ids.map(String) : []), ...subjects.flatMap((subject) => Array.isArray(subject.roles) ? subject.roles.map(String) : [])])].sort(), [contract, subjects])
  const relations = useMemo(() => Array.isArray(contract.relations) ? contract.relations as Item[] : [], [contract])
  const rules = useMemo(() => expandedRules(contract), [contract])
  const related = useMemo(() => {
    if (!focus) return new Set<string>()
    const values = new Set<string>([`subject:${focus}`])
    const subject = subjects.find((item) => text(item.subject_id) === focus)
    for (const role of subject?.roles ?? []) values.add(`role:${String(role)}`)
    for (const relation of relations) { const source = endpointId(relation.source); const target = endpointId(relation.target); if (source === `subject:${focus}` || target === `subject:${focus}`) { values.add(source); values.add(target) } }
    for (const rule of rules) if (text(rule.subject_id) === focus) values.add(`resource:${text(rule.resource_id)}`)
    return values
  }, [focus, relations, rules, subjects])
  const graph = useMemo(() => {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const position = (index: number, total: number) => 70 + index * Math.max(95, 500 / Math.max(1, total - 1))
    roles.forEach((role, index) => nodes.push({ id: `role:${role}`, ariaLabel: `角色 ${role}`, position: { x: 0, y: position(index, roles.length) }, sourcePosition: Position.Right, targetPosition: Position.Left, data: { label: nodeLabel('角色', role) }, style: { width: 170, borderColor: '#7c3aed', opacity: focus && !related.has(`role:${role}`) ? 0.18 : 1 } }))
    subjects.forEach((subject, index) => nodes.push({ id: `subject:${text(subject.subject_id)}`, ariaLabel: `身份 ${text(subject.subject_id)}`, position: { x: 310, y: position(index, subjects.length) }, sourcePosition: Position.Right, targetPosition: Position.Left, data: { label: nodeLabel('身份', text(subject.subject_id), (subject.roles ?? []).map(String).join('、')) }, style: { width: 190, borderColor: '#1677ff', opacity: focus && !related.has(`subject:${text(subject.subject_id)}`) ? 0.18 : 1 } }))
    resources.forEach((resource, index) => nodes.push({ id: `resource:${text(resource.resource_id)}`, ariaLabel: `资源 ${text(resource.resource_id)}`, position: { x: 680, y: position(index, resources.length) }, sourcePosition: Position.Right, targetPosition: Position.Left, data: { label: nodeLabel('资源', text(resource.resource_id), text(resource.resource_type)) }, style: { width: 190, borderColor: '#08979c', opacity: focus && !related.has(`resource:${text(resource.resource_id)}`) ? 0.18 : 1 } }))
    subjects.forEach((subject) => (subject.roles ?? []).forEach((role: unknown) => edges.push({ id: `role-${String(role)}-${text(subject.subject_id)}`, source: `role:${String(role)}`, target: `subject:${text(subject.subject_id)}`, label: '包含身份', type: 'smoothstep', style: { stroke: '#7c3aed', opacity: focus && (!related.has(`role:${String(role)}`) || !related.has(`subject:${text(subject.subject_id)}`)) ? 0.12 : 0.8 } })))
    relations.forEach((relation, index) => edges.push({ id: `relation-${text(relation.relation_id)}-${index}`, source: endpointId(relation.source), target: endpointId(relation.target), label: text(relation.relation), markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#64748b', opacity: focus && (!related.has(endpointId(relation.source)) || !related.has(endpointId(relation.target))) ? 0.12 : 0.9 } }))
    rules.forEach((rule, index) => edges.push({ id: `rule-${text(rule.rule_id)}-${text(rule.resource_id)}-${index}`, source: `subject:${text(rule.subject_id)}`, target: `resource:${text(rule.resource_id)}`, label: `${text(rule.action_id)} · ${expectationLabel(rule.expectation)}`, type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: String(rule.expectation) === 'ALLOW' ? '#16a34a' : '#dc2626', strokeDasharray: '6 4', opacity: focus && (!related.has(`subject:${text(rule.subject_id)}`) || !related.has(`resource:${text(rule.resource_id)}`)) ? 0.12 : 0.9 } }))
    return { nodes, edges }
  }, [focus, related, relations, resources, roles, rules, subjects])
  const visibleRelations = focus ? relations.filter((relation) => related.has(endpointId(relation.source)) && related.has(endpointId(relation.target))) : relations
  const visibleRules = focus ? rules.filter((rule) => text(rule.subject_id) === focus) : rules
  return <Space direction="vertical" className="full-width" size="middle">
    <Space wrap><Select allowClear aria-label="聚焦身份" placeholder="全局总览：选择身份后聚焦" value={focus} onChange={setFocus} style={{ minWidth: 260 }} options={subjects.map((subject) => ({ value: text(subject.subject_id), label: text(subject.subject_id) }))} /><Tag color={focus ? 'blue' : 'default'}>{focus ? `正在聚焦：${focus}` : '全局总览'}</Tag><Typography.Text type="secondary">可拖动画布、滚轮缩放，并用右下角控件自动适配视图。</Typography.Text></Space>
    <Space wrap aria-label="关系图图例"><Typography.Text type="secondary">图例：</Typography.Text><Tag color="purple">角色</Tag><Tag color="blue">身份</Tag><Tag color="cyan">资源</Tag><Tag color="green">允许规则</Tag><Tag color="red">拒绝规则</Tag><Typography.Text type="secondary">虚线表示权限规则，实线表示角色或资源关系。</Typography.Text></Space>
    <div className="permission-flow" role="region" aria-label="权限关系图">
      <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.25} maxZoom={2} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => { if (node.id.startsWith('subject:')) setFocus(node.id.slice('subject:'.length)) }}>
        <Background gap={20} size={1} />
        <MiniMap pannable zoomable nodeColor={(node) => node.id.startsWith('role:') ? '#7c3aed' : node.id.startsWith('subject:') ? '#1677ff' : '#08979c'} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
    <div className="permission-graph-lists"><Card size="small" title={focus ? '当前身份的关系' : '完整关系列表'}><List size="small" dataSource={visibleRelations} locale={{ emptyText: '未声明关系' }} renderItem={(relation) => <List.Item><Typography.Text>{text(relation.source?.endpoint_id)} — {text(relation.relation)} → {text(relation.target?.endpoint_id)}</Typography.Text></List.Item>} /></Card><Card size="small" title={focus ? '当前身份的权限' : '完整权限列表'}><List size="small" dataSource={visibleRules} locale={{ emptyText: '未声明权限规则' }} renderItem={(rule) => <List.Item><Typography.Text>{text(rule.subject_id)} — {text(rule.action_id)} / {expectationLabel(rule.expectation)} → {text(rule.resource_id)}</Typography.Text></List.Item>} /></Card></div>
  </Space>
}

export function PermissionExplorer({ contract }: { contract: Item }) {
  return <Tabs items={[{ key: 'matrix', label: '权限矩阵', children: <PermissionMatrix contract={contract} /> }, { key: 'graph', label: '关系图', children: <PermissionGraph contract={contract} /> }]} />
}
