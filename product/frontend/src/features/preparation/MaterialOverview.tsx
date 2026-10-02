// 五类材料使用同一次准备投影；分组完整性由全部子项决定，不把部分可用写成全部可复用。
import { useState, type ReactNode } from 'react'
import { Button } from 'antd'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { UserOutlined, VideoCameraOutlined, DatabaseOutlined, FileTextOutlined, ToolOutlined } from '@ant-design/icons'
import type { ActionPreparation, MaterialReference, PreparationItem } from '../../api/preparation'
import type { PreparationMaterialAdvice } from '../../api/preparationGuidance'
import './materials.css'

export function MaterialOverview({ action, effectName, currentStage, taskTitle, taskWhy, primary, onIdentity, onMaterial, children, returnKind, showFocus = true, outdated = false, advice }: {
  action: ActionPreparation; effectName: (id: string) => string; currentStage?: number
  taskTitle?: string; taskWhy?: string; primary: ReactNode; onIdentity: () => void
  onMaterial: (reference: MaterialReference, label: string) => void; children?: ReactNode
  returnKind?: string
  showFocus?: boolean
  outdated?: boolean
  advice?: PreparationMaterialAdvice[]
}) {
  const [expanded, setExpanded] = useState<string | undefined>(returnKind)
  const ref = (kind: MaterialReference['kind'], member_id: string | null = null): MaterialReference => ({ kind, member_id, action_id: action.action_id, action_revision: action.action_revision })
  const slotName = (id: string) => { const slot = action.identity_requirements.slots.find(item => item.requirement.slot_id === id); return slot ? `${slot.actor_display_name}账号 ${slot.requirement.ordinal}` : '指定所有者账号' }
  const groups: Array<{ key: string; title: string; icon: ReactNode; items: Array<{ label: string; value: PreparationItem; reference?: MaterialReference }> }> = [
    { key: 'identity', title: '真实账号', icon: <UserOutlined />, items: action.identity_requirements.slots.map(item => ({ label: slotName(item.requirement.slot_id), value: item })) },
    { key: 'execution', title: '动作录制', icon: <VideoCameraOutlined />, items: [{ label: action.display_name, value: action.execution, reference: ref('execution') }] },
    { key: 'resource', title: '测试资源', icon: <DatabaseOutlined />, items: action.resources.map(item => ({ label: `${slotName(item.owner_slot_id)}拥有的资源`, value: item, reference: item.owner_test_identity_id ? ref('resource', item.owner_test_identity_id) : undefined })) },
    { key: 'evidence', title: '结果证明', icon: <FileTextOutlined />, items: action.effect_evidence.map(item => ({ label: effectName(item.effect_id), value: item, reference: ref('evidence', item.effect_id) })) },
    { key: 'recovery', title: '恢复方式', icon: <ToolOutlined />, items: [{ label: action.recovery.status === 'NOT_REQUIRED' ? '只读动作无需恢复' : '恢复本次操作改变的状态', value: action.recovery, reference: ref('recovery') }] },
  ]
  const complete = (items: Array<{ value: PreparationItem }>) => items.length > 0 && items.every(item => ['SATISFIED', 'NOT_REQUIRED'].includes(item.value.status))
  const reusable = groups.filter(group => complete(group.items) && group.items.some(item => item.value.status === 'SATISFIED')).length
  const unnecessary = groups.filter(group => group.items.length === 0 || group.items.every(item => item.value.status === 'NOT_REQUIRED')).length
  const status = (items: Array<{ value: PreparationItem }>) => !items.length || items.every(item => item.value.status === 'NOT_REQUIRED') ? '无需准备' : complete(items) ? '可复用' : items.some(item => item.value.status === 'BLOCKED') ? '需要先确认' : items.some(item => item.value.binding_fingerprint || item.value.status === 'STALE') ? '已保存，需复核' : '需要准备'
  const details = (kind: string, item: {value: PreparationItem; reference?: MaterialReference}) => advice?.find(entry => entry.action_id === action.action_id && entry.action_revision === action.action_revision && entry.kind === kind && entry.status === item.value.status && entry.member_id === (kind === 'identity' ? (item.value as {test_identity_id?: string}).test_identity_id : item.reference?.member_id ?? null))
  const retained = groups.filter(group => complete(group.items) && group.items.some(item => item.value.status === 'SATISFIED')).map(group => group.title)
  return <>
    {showFocus && <section className="material-focus" aria-label="当前需要处理的材料"><div><StatusBadge kind="preparation" tone={action.preparation_complete && !outdated ? 'neutral' : 'warning'}>{outdated ? '等待同步' : action.preparation_complete ? '材料已齐备' : '需要处理'}</StatusBadge>
      <h2>{outdated ? '先核对当前材料状态' : taskTitle ?? (action.preparation_complete ? '材料可以继续使用' : '核对这项动作的准备条件')}</h2>
      <p className="editorial-muted">{outdated ? '已保存的材料仍保留，当前可用性需要重新同步。' : taskWhy ?? '只更新需要处理的部分，已确认的其他材料继续保留。'}</p>{!outdated && retained.length > 0 && <p className="material-retained">可沿用：{retained.join('、')}。</p>}</div>
      <p className="material-count">{outdated ? '上次核对' : '已核对'} <strong>5</strong> 类材料，<strong>{reusable}</strong> 类{outdated ? '当时可用' : '可继续使用'}{unnecessary > 0 && <small>{unnecessary} 类无需准备</small>}</p><div className="material-focus-actions">{primary}</div></section>}
    <div className="material-table" role="table" aria-label="检查材料清单">
      <div className="material-table-head" role="row"><span role="columnheader">材料</span><span role="columnheader">当前情况</span><span role="columnheader">适用内容</span><span role="columnheader">操作</span></div>
      {groups.map((group, index) => <div key={group.key} className={`material-group ${currentStage === index ? 'is-current' : ''}`}>
        <div className="material-row" role="row"><span role="cell" className="material-row-title">{group.icon}{group.title}</span>
          <span role="cell"><StatusBadge kind="preparation" tone={(complete(group.items) || status(group.items) === '无需准备') && !outdated ? 'neutral' : 'warning'}>{outdated ? '上次：' : ''}{status(group.items)}</StatusBadge></span>
          <span role="cell" className="material-row-summary">{group.items.map(item => item.label).join('、') || '当前动作没有此项要求'}</span>
          <span role="cell"><Button type="link" aria-expanded={expanded === group.key} onClick={() => setExpanded(value => value === group.key ? undefined : group.key)}>{currentStage === index ? '处理' : '查看'}</Button></span></div>
        {expanded === group.key && <div className="material-row-detail">{group.items.map((item, i) => <div key={i}><div><strong>{item.label}</strong><p className="editorial-muted">{!outdated ? details(group.key, item)?.reason ?? status([item]) : `上次：${status([item])}`}</p></div>
          {group.key === 'identity' ? <Button onClick={onIdentity}>管理测试账号</Button> : item.reference && item.value.status !== 'NOT_REQUIRED' ? <Button data-material-key={`${item.reference.kind}:${item.reference.member_id ?? ''}`} onClick={() => onMaterial(item.reference!, item.label)}>查看与更新</Button> : <span className="editorial-muted">{item.value.status === 'NOT_REQUIRED' ? '不需要额外材料' : '先确认所需账号'}</span>}</div>)}</div>}
      </div>)}
    </div>
    <details className="material-dependencies"><summary>查看材料依赖与适用范围</summary><p>材料仅用于当前应用和这项业务修订。账号、资源所有者、源码或目标地址变化后，界鉴会重新核对相关材料。</p><p>已保存的录制不等于本轮检查事实。正式检查会重新执行并形成独立证据。</p>{children}</details>
  </>
}
