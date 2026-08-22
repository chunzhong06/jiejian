/* 只读关系看板：用稳定的行式布局呈现业务关系，避免无限画布缩放后失去可读性。 */

import { useMemo, useState } from 'react'
import { Empty, Select, Space, Tag, Typography } from 'antd'
import type { PermissionContractDto } from '../../../api/contracts'
import { productTermLabel } from '../../../app/presentation'
import { buildFocusedRelationshipGraph, buildGlobalRelationshipGraph } from './projection'
import type { RelationshipEdge, RelationshipNode } from './types'

function EntityCard({ node, onFocus }: { node?: RelationshipNode; onFocus: (subjectId: string) => void }) {
  if (!node) return null
  const content = <>
    <Typography.Text type="secondary">{node.kind === 'identity' ? '身份' : '资源'}</Typography.Text>
    <Typography.Text strong>{node.label}</Typography.Text>
    <Typography.Text className="permission-raw-id" type="secondary">{node.rawId}</Typography.Text>
    {node.kind === 'identity' && <Space size={[4, 4]} wrap>{(node.roles ?? []).map((role) => <Tag key={role}>{role}</Tag>)}</Space>}
    {node.kind === 'resource' && node.secondary && <Tag>{node.secondary}</Tag>}
  </>
  if (node.kind === 'identity') {
    return <button type="button" className="permission-entity-card permission-entity-identity" aria-label={`身份 ${node.rawId}`} onClick={() => onFocus(node.rawId)}>{content}</button>
  }
  return <div className="permission-entity-card permission-entity-resource" aria-label={`资源 ${node.rawId}`}>{content}</div>
}

function RelationshipRow({ edge, nodes, onFocus }: { edge: RelationshipEdge; nodes: Map<string, RelationshipNode>; onFocus: (subjectId: string) => void }) {
  const permission = edge.kind === 'permission'
  const expectation = edge.expectation === 'ALLOW' ? 'allow' : edge.expectation === 'DENY' ? 'deny' : 'neutral'
  return <div className={`permission-relation-row permission-relation-${permission ? `permission-${expectation}` : edge.kind}`}>
    <EntityCard node={nodes.get(edge.source)} onFocus={onFocus} />
    <div className="permission-relation-connector">
      <span className="permission-relation-line" aria-hidden="true" />
      <Tag color={permission ? expectation === 'allow' ? 'green' : expectation === 'deny' ? 'red' : 'default' : edge.kind === 'ownership' ? 'cyan' : 'purple'}>{edge.label}</Tag>
      <span className="permission-relation-arrow" aria-hidden="true">→</span>
    </div>
    <EntityCard node={nodes.get(edge.target)} onFocus={onFocus} />
  </div>
}

export function PermissionGraph({ contract }: { contract: PermissionContractDto }) {
  const [focus, setFocus] = useState<string>()
  const subjects = useMemo(() => [...(contract.subjects ?? [])].sort((left, right) => left.subject_id.localeCompare(right.subject_id)), [contract])
  const model = useMemo(() => focus ? buildFocusedRelationshipGraph(contract, focus) : buildGlobalRelationshipGraph(contract), [contract, focus])
  const nodes = useMemo(() => new Map(model.nodes.map((node) => [node.id, node])), [model])
  const relations = model.edges.filter((edge) => edge.kind !== 'permission')
  const permissions = model.edges.filter((edge) => edge.kind === 'permission')
  const connectedNodeIds = new Set(model.edges.flatMap((edge) => [edge.source, edge.target]))
  const unlinkedNodes = model.nodes.filter((node) => !connectedNodeIds.has(node.id))

  return <Space direction="vertical" className="full-width" size="middle">
    <Space wrap>
      <Select allowClear aria-label="聚焦身份" placeholder="全局总览：选择身份后聚焦" value={focus} onChange={setFocus} style={{ minWidth: 260 }} options={subjects.map((subject) => ({ value: subject.subject_id, label: productTermLabel('identity', subject.subject_id, false) }))} />
      <Tag color={focus ? 'blue' : 'default'}>{focus ? `正在聚焦：${productTermLabel('identity', focus, false)}` : '全局业务关系'}</Tag>
      <Typography.Text type="secondary">点击身份可聚焦查看其业务关系与权限规则；协议标识保留在中文名称下方。</Typography.Text>
    </Space>
    <Space wrap aria-label="关系图图例"><Typography.Text type="secondary">图例：</Typography.Text><Tag color="blue">身份</Tag><Tag color="cyan">资源</Tag><Tag color="purple">业务关系</Tag><Tag color="cyan">资源归属</Tag>{focus && <><Tag color="green">允许</Tag><Tag color="red">拒绝</Tag></>}</Space>
    <div className="permission-relationship-board" role="region" aria-label="权限关系图">
      <section className="permission-relation-section" aria-labelledby="business-relations-title">
        <div className="permission-section-heading"><Typography.Title level={5} id="business-relations-title">{focus ? '当前身份的业务关系' : '完整业务关系'}</Typography.Title><Typography.Text type="secondary">共 {relations.length} 条</Typography.Text></div>
        {relations.length > 0 ? <div className="permission-relation-list">{relations.map((edge) => <RelationshipRow key={edge.id} edge={edge} nodes={nodes} onFocus={setFocus} />)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未声明业务关系" />}
      </section>
      {focus && <section className="permission-relation-section" aria-labelledby="permission-relations-title">
        <div className="permission-section-heading"><Typography.Title level={5} id="permission-relations-title">当前身份的权限</Typography.Title><Typography.Text type="secondary">共 {permissions.length} 条</Typography.Text></div>
        {permissions.length > 0 ? <div className="permission-relation-list">{permissions.map((edge) => <RelationshipRow key={edge.id} edge={edge} nodes={nodes} onFocus={setFocus} />)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前身份没有权限规则" />}
      </section>}
      {unlinkedNodes.length > 0 && <section className="permission-relation-section" aria-labelledby="unlinked-entities-title">
        <div className="permission-section-heading"><Typography.Title level={5} id="unlinked-entities-title">未关联实体</Typography.Title><Typography.Text type="secondary">这些身份或资源尚未出现在当前关系中</Typography.Text></div>
        <div className="permission-unlinked-grid">{unlinkedNodes.map((node) => <EntityCard key={node.id} node={node} onFocus={setFocus} />)}</div>
      </section>}
      {!focus && <div className="permission-board-hint"><Typography.Text type="secondary">全局总览只展示业务关系。选择或点击身份后，才显示该身份自己的允许与拒绝规则。</Typography.Text></div>}
    </div>
  </Space>
}
