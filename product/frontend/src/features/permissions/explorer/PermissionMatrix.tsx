/* 权限矩阵视图：只负责筛选、单元格展示和规则详情，不解释原始契约。 */

import { useMemo, useState } from 'react'
import { Alert, Button, Collapse, Descriptions, Drawer, List, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { expectationLabel, productTermLabel, severityLabel } from '../../../app/presentation'
import type { ExpandedPermissionRule, PermissionCellState, PermissionMatrixModel, PermissionMatrixRow } from './types'

type CellSelection = {
  row: PermissionMatrixRow
  actionId: string
  resourceId: string
  resourceType?: string
  rules: ExpandedPermissionRule[]
  state: PermissionCellState
}

function contextSummary(value: Record<string, unknown> | undefined) {
  if (!value || Object.keys(value).length === 0) return '无附加条件'
  return Object.entries(value)
    .filter(([, item]) => item !== undefined && item !== null)
    .map(([key, item]) => `${key}：${Array.isArray(item) ? item.join('、') : String(item)}`)
    .join('；') || '无附加条件'
}

function stateView(state: PermissionCellState) {
  if (state === 'ALLOW') return { label: '允许', color: 'green', explanation: '规则明确允许该身份对这个资源执行此动作。' }
  if (state === 'DENY') return { label: '拒绝', color: 'red', explanation: '规则明确拒绝该身份对这个资源执行此动作。' }
  if (state === 'CONFLICT') return { label: '规则冲突', color: 'gold', explanation: '同一单元格同时命中了不一致的期望，需要先消除冲突。' }
  return { label: '未声明', color: 'default', explanation: '当前契约没有声明这一身份、动作和资源组合。' }
}

export function PermissionMatrix({ model }: { model: PermissionMatrixModel }) {
  const [subjectFilter, setSubjectFilter] = useState<string>()
  const [roleFilter, setRoleFilter] = useState<string>()
  const [actionFilter, setActionFilter] = useState<string>()
  const [resourceFilter, setResourceFilter] = useState<string>()
  const [selected, setSelected] = useState<CellSelection>()
  const visibleRows = useMemo(() => model.rows.filter((row) =>
    (!subjectFilter || row.subject.subject_id === subjectFilter)
    && (!roleFilter || (row.subject.roles ?? []).includes(roleFilter))), [model.rows, roleFilter, subjectFilter])
  const visibleActions = model.actions.filter((actionId) => !actionFilter || actionId === actionFilter)
  const visibleResources = model.resources.filter((resource) => !resourceFilter || resource.resource_id === resourceFilter)
  const columns: TableColumnsType<PermissionMatrixRow> = [
    {
      title: '身份 / 角色', key: 'subject', fixed: 'left', width: 220,
      render: (_, row) => <Space direction="vertical" size={0}>
        <Typography.Text strong>{productTermLabel('identity', row.subject.subject_id, false)}</Typography.Text>
        <Typography.Text type="secondary" className="permission-raw-id">{row.subject.subject_id}</Typography.Text>
        <Space size={[4, 4]} wrap>{(row.subject.roles ?? []).map((role) => <Tag key={role}>{productTermLabel('role', role, false)}</Tag>)}</Space>
      </Space>,
    },
    ...visibleActions.map((actionId) => ({
      title: <Space direction="vertical" size={0}><Typography.Text strong>{productTermLabel('action', actionId, false)}</Typography.Text><Typography.Text type="secondary">{actionId}</Typography.Text></Space>,
      key: `action:${actionId}`,
      children: visibleResources.map((resource) => ({
        title: <Space direction="vertical" size={0}><Typography.Text>{productTermLabel('resource', resource.resource_id, false)}</Typography.Text><Typography.Text type="secondary">{resource.resource_id}</Typography.Text></Space>,
        key: `${actionId}:${resource.resource_id}`,
        width: 170,
        align: 'center' as const,
        render: (_: unknown, row: PermissionMatrixRow) => {
          const cell = row.cells[`${actionId}:${resource.resource_id}`]
          const view = stateView(cell.state)
          return <Button className="permission-cell" type="text" aria-label={`${row.subject.subject_id} ${actionId} ${resource.resource_id} ${view.label}`} onClick={() => setSelected({ row, actionId, resourceId: resource.resource_id, resourceType: resource.resource_type, rules: cell.rules, state: cell.state })}><Tag color={view.color}>{view.label}</Tag></Button>
        },
      })),
    })),
  ]

  return <Space direction="vertical" className="full-width" size="middle">
    <Space wrap>
      <Select allowClear aria-label="筛选身份" placeholder="筛选身份" value={subjectFilter} onChange={setSubjectFilter} style={{ minWidth: 160 }} options={model.subjects.map((item) => ({ value: item.subject_id, label: productTermLabel('identity', item.subject_id, false) }))} />
      <Select allowClear aria-label="筛选角色" placeholder="筛选角色" value={roleFilter} onChange={setRoleFilter} style={{ minWidth: 160 }} options={model.roles.map((item) => ({ value: item, label: productTermLabel('role', item, false) }))} />
      <Select allowClear aria-label="筛选动作" placeholder="筛选动作" value={actionFilter} onChange={setActionFilter} style={{ minWidth: 160 }} options={model.actions.map((item) => ({ value: item, label: productTermLabel('action', item, false) }))} />
      <Select allowClear aria-label="筛选资源" placeholder="筛选资源" value={resourceFilter} onChange={setResourceFilter} style={{ minWidth: 180 }} options={model.resources.map((item) => ({ value: item.resource_id, label: productTermLabel('resource', item.resource_id, false) }))} />
    </Space>
    <Space wrap aria-label="矩阵图例"><Typography.Text type="secondary">图例：</Typography.Text>{(['ALLOW', 'DENY', 'UNDECLARED', 'CONFLICT'] as PermissionCellState[]).map((state) => { const view = stateView(state); return <Tag key={state} color={view.color}>{view.label}</Tag> })}</Space>
    {(visibleActions.length === 0 || visibleResources.length === 0) && <Alert type="info" showIcon message="当前筛选范围没有可展示的动作与资源组合。" />}
    <Table<PermissionMatrixRow> className="permission-matrix" sticky columns={columns} dataSource={visibleRows} pagination={false} size="small" scroll={{ x: 'max-content', y: 480 }} locale={{ emptyText: '当前筛选范围没有身份。' }} />
    <Drawer width={560} open={Boolean(selected)} onClose={() => setSelected(undefined)} title={selected ? `${productTermLabel('identity', selected.row.subject.subject_id, false)} · ${productTermLabel('action', selected.actionId, false)} · ${productTermLabel('resource', selected.resourceId, false)}` : '权限详情'}>
      {selected && <Space direction="vertical" className="full-width" size="middle">
        <Alert showIcon type={selected.state === 'DENY' ? 'error' : selected.state === 'CONFLICT' ? 'warning' : selected.state === 'ALLOW' ? 'success' : 'info'} message={stateView(selected.state).label} description={stateView(selected.state).explanation} />
        <Descriptions size="small" column={1} bordered>
          <Descriptions.Item label="身份">{productTermLabel('identity', selected.row.subject.subject_id, false)}（{selected.row.subject.subject_id}）</Descriptions.Item>
          <Descriptions.Item label="动作">{productTermLabel('action', selected.actionId, false)}（{selected.actionId}）</Descriptions.Item>
          <Descriptions.Item label="资源">{productTermLabel('resource', selected.resourceId, false)}（{selected.resourceId}）；类型：{productTermLabel('resourceType', selected.resourceType, false)}</Descriptions.Item>
        </Descriptions>
        <List size="small" header={<Typography.Text strong>命中的规则</Typography.Text>} dataSource={selected.rules} locale={{ emptyText: '没有命中规则' }} renderItem={(rule) => <List.Item><Space direction="vertical" className="full-width"><Space wrap><Tag color={rule.expectation === 'ALLOW' ? 'green' : 'red'}>{expectationLabel(rule.expectation)}</Tag><Tag>{severityLabel(rule.severity)}</Tag></Space><Typography.Text>关系：{(rule.relation_path ?? []).map((item) => productTermLabel('relation', item, false)).join(' → ') || '无关系限制'}</Typography.Text><Typography.Text>条件：{contextSummary(rule.context)}</Typography.Text><Typography.Text>核验：{(rule.required_observations ?? []).join('、') || '未声明必需观察'}</Typography.Text><Collapse ghost items={[{ key: 'rule-tech', label: '高级：规则标识', children: <Typography.Text code>{rule.rule_id ?? rule.id ?? '未提供'}</Typography.Text> }]} /></Space></List.Item>} />
      </Space>}
    </Drawer>
  </Space>
}
