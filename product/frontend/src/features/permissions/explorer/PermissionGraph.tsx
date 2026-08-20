/* 只读权限关系图：全局展示业务关系，聚焦时才叠加当前身份的权限边。 */

import { useMemo, useState } from 'react'
import { Card, List, Select, Space, Tag, Typography } from 'antd'
import { Background, Controls, Handle, MarkerType, Panel, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { PermissionContractDto } from '../../../api/contracts'
import { productTermLabel } from '../../../app/presentation'
import { buildFocusedRelationshipGraph, buildGlobalRelationshipGraph } from './projection'
import type { RelationshipGraphModel, RelationshipNode } from './types'

type EntityNode = Node<{ model: RelationshipNode }, 'permission-entity'>

function PermissionEntityNode({ data }: NodeProps<EntityNode>) {
  const node = data.model
  return <div className={`permission-entity-node permission-entity-${node.kind}`}>
    <Typography.Text type="secondary">{node.kind === 'identity' ? '身份' : '资源'}</Typography.Text>
    <Typography.Text strong>{node.label}</Typography.Text>
    <Typography.Text className="permission-raw-id" type="secondary">{node.rawId}</Typography.Text>
    {node.kind === 'identity' && <Space size={[4, 4]} wrap>{(node.roles ?? []).map((role) => <Tag key={role}>{role}</Tag>)}</Space>}
    {node.kind === 'resource' && node.secondary && <Tag>{node.secondary}</Tag>}
    <Handle id="relation-in" className="permission-handle permission-handle-relation" type="target" position={Position.Top} style={{ left: '42%' }} />
    <Handle id="relation-out" className="permission-handle permission-handle-relation" type="source" position={Position.Bottom} style={{ left: '42%' }} />
    <Handle id="ownership-in" className="permission-handle permission-handle-ownership" type="target" position={Position.Left} style={{ top: '38%' }} />
    <Handle id="ownership-out" className="permission-handle permission-handle-ownership" type="source" position={Position.Right} style={{ top: '38%' }} />
    <Handle id="permission-in" className="permission-handle permission-handle-rule" type="target" position={Position.Left} style={{ top: '72%' }} />
    <Handle id="permission-out" className="permission-handle permission-handle-rule" type="source" position={Position.Right} style={{ top: '72%' }} />
  </div>
}

const nodeTypes = { 'permission-entity': PermissionEntityNode }

function reactFlowGraph(model: RelationshipGraphModel) {
  const nodes: EntityNode[] = model.nodes.map((node) => ({
    id: node.id,
    type: 'permission-entity',
    ariaLabel: `${node.kind === 'identity' ? '身份' : '资源'} ${node.rawId}`,
    position: node.position,
    data: { model: node },
  }))
  const edges: Edge[] = model.edges.map((edge) => {
    const permission = edge.kind === 'permission'
    const ownership = edge.kind === 'ownership'
    const color = permission ? edge.expectation === 'ALLOW' ? '#22c55e' : '#ef4444' : ownership ? '#22d3ee' : '#a78bfa'
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: permission ? 'permission-out' : ownership ? 'ownership-out' : 'relation-out',
      targetHandle: permission ? 'permission-in' : ownership ? 'ownership-in' : 'relation-in',
      label: edge.label,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color },
      className: `permission-edge permission-edge-${edge.kind}`,
      style: { stroke: color, strokeWidth: permission ? 2 : 1.6, strokeDasharray: permission ? '7 5' : undefined },
      labelStyle: { fill: '#e2e8f0', fontSize: 12 },
      labelBgStyle: { fill: '#0f172a', fillOpacity: 0.82 },
      labelBgPadding: [6, 4] as [number, number],
      labelBgBorderRadius: 4,
    }
  })
  return { nodes, edges }
}

export function PermissionGraph({ contract }: { contract: PermissionContractDto }) {
  const [focus, setFocus] = useState<string>()
  const subjects = useMemo(() => [...(contract.subjects ?? [])].sort((left, right) => left.subject_id.localeCompare(right.subject_id)), [contract])
  const model = useMemo(() => focus ? buildFocusedRelationshipGraph(contract, focus) : buildGlobalRelationshipGraph(contract), [contract, focus])
  const graph = useMemo(() => reactFlowGraph(model), [model])
  const relations = model.edges.filter((edge) => edge.kind !== 'permission')
  const permissions = model.edges.filter((edge) => edge.kind === 'permission')
  const focusedWithoutEdges = Boolean(focus && model.edges.length === 0)

  return <Space direction="vertical" className="full-width" size="middle">
    <Space wrap>
      <Select allowClear aria-label="聚焦身份" placeholder="全局总览：选择身份后聚焦" value={focus} onChange={setFocus} style={{ minWidth: 260 }} options={subjects.map((subject) => ({ value: subject.subject_id, label: productTermLabel('identity', subject.subject_id, false) }))} />
      <Tag color={focus ? 'blue' : 'default'}>{focus ? `正在聚焦：${productTermLabel('identity', focus, false)}` : '全局业务关系'}</Tag>
      <Typography.Text type="secondary">可拖动节点和画布、滚轮缩放，并用右下角控件自动适配视图。</Typography.Text>
    </Space>
    <Space wrap aria-label="关系图图例"><Typography.Text type="secondary">图例：</Typography.Text><Tag color="blue">身份</Tag><Tag color="cyan">资源</Tag><Tag color="purple">业务关系</Tag><Tag color="cyan">资源归属</Tag>{focus && <><Tag color="green">允许</Tag><Tag color="red">拒绝</Tag></>}</Space>
    <div className="permission-flow" role="region" aria-label="权限关系图">
      <ReactFlow key={`${model.mode}:${model.focusSubjectId ?? 'all'}`} nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1.15 }} minZoom={0.35} maxZoom={1.8} nodesConnectable={false} proOptions={{ hideAttribution: true }} onNodeClick={(_, node) => { if (node.id.startsWith('subject:')) setFocus(node.id.slice('subject:'.length)) }}>
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
        {focusedWithoutEdges && <Panel position="top-right" className="permission-flow-note">当前身份没有直接关系或权限规则</Panel>}
      </ReactFlow>
    </div>
    <div className="permission-graph-lists">
      <Card size="small" title={focus ? '当前身份的业务关系' : '完整业务关系列表'}><List size="small" dataSource={relations} locale={{ emptyText: '未声明业务关系' }} renderItem={(edge) => <List.Item><Typography.Text>{edge.label}</Typography.Text><Typography.Text type="secondary">{edge.source.replace(/^[^:]+:/, '')} → {edge.target.replace(/^[^:]+:/, '')}</Typography.Text></List.Item>} /></Card>
      <Card size="small" title={focus ? '当前身份的权限' : '权限说明'}>{focus ? <List size="small" dataSource={permissions} locale={{ emptyText: '当前身份没有权限规则' }} renderItem={(edge) => <List.Item><Typography.Text>{edge.label}</Typography.Text><Typography.Text type="secondary">{edge.target.replace('resource:', '')}</Typography.Text></List.Item>} /> : <Typography.Text type="secondary">全局图只展示业务关系；选择身份后显示该身份自己的允许或拒绝边。</Typography.Text>}</Card>
    </div>
  </Space>
}
