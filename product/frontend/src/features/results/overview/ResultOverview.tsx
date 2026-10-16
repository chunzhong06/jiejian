// 结果总览只压缩服务端已发布文案；未知文案原样显示，不根据 HTTP 或效果推算单项结论。
import { Button, Modal } from 'antd'
import { useContext, useEffect, useState, type ReactNode } from 'react'
import {RequirementScopeSummary} from '../../../shared/ui/RequirementScopeSummary'
import { WorkPageVisible } from '../../../shared/runtime/visibility'
import type { ActionResultStory, ResultStory } from '../../../api/checks/currentChecks'
import { repairLabels } from '../../../api/checks/repairs'
import { StatusBadge, type StatusTone } from '../../../shared/ui/StatusBadge'
import { ResultAgentHandoff } from '../ResultAgentHandoff'
import { effectSentence, effectScope, runHeading } from './resultLanguage'

const judgements: Record<string, { label: string; tone: string }> = {
  '本次权限要求已得到验证': { label: '符合要求', tone: 'pass' },
  '已确认不应发生的业务后果': { label: '违反要求', tone: 'block' },
  '现有证据不足以完成判断': { label: '无法确定', tone: 'unknown' },
  '检查结果符合已批准的权限要求': { label: '符合要求', tone: 'pass' },
  '已发现规则禁止的实际结果': { label: '违反要求', tone: 'block' },
  '证据或检查条件不足，尚不能确定': { label: '无法确定', tone: 'unknown' },
}
export function caseJudgement(action: ActionResultStory) {
  return judgements[action.judgement] ?? { label: action.judgement, tone: 'neutral' }
}
export function resourceOwner(action: ActionResultStory) {
  return action.fact_comparison.planned_resource_owner?.label ?? (action.permission.relation === 'OWNS' ? '自己' : action.permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '另一个同权限组账号' : '原资源所有者')
}
export function ResultBadge({ tone, children }: { tone: string; children: ReactNode }) {
  const tones: Record<string, StatusTone> = { pass: 'success', block: 'danger', unknown: 'warning' }
  return <StatusBadge kind="verdict" tone={tones[tone] ?? 'neutral'} className={`result-badge is-${tone}`}>{children}</StatusBadge>
}
export function BusinessEffects({ action }: { action: ActionResultStory }) {
  const effects = action.fact_comparison.effects
  return <>{effects.length ? effects.map(effect => {
    // 旧Story可能同时给出ABSENT与未闭合说明；只能翻译服务端已确认的否定，不能抹去限制。
    const absentConfirmed = ['在已闭合的观察范围内未发生这项业务结果', '本次观察已完成，未发现这项结果'].includes(effect.judgement)
    const state = effect.observed_state === 'ABSENT' && !absentConfirmed ? 'UNKNOWN' : effect.observed_state
    return <div className="result-effect-fact" key={effect.effect_id}><strong>{effectSentence(effect.business_label, state)}</strong><span>{effectScope(state)}</span></div>
  }) : <span className="editorial-muted">尚未取得足以说明实际结果的记录。</span>}</>
}
const summaries = {
  PASS: '后续代码变化需要新的检查。',
  BLOCK: '先查看哪项操作违反了规则及其证据。修复后重新检查，同时确认允许的功能仍能正常使用。',
  INCONCLUSIVE: '查看未完成的检查、缺少的证据或不满足的条件。处理后需要重新检查。',
}
export function ResultOverviewHeader({ story, onNavigate, historicalOnly, action }: {
  story: ResultStory; onNavigate?: (path: string) => void; historicalOnly?: boolean
  action?: { label: string; onClick: () => void }
}) {
  const repair = story.verdict === 'BLOCK' ? story.actions.find(item => item.repair_requirement)?.repair_requirement : null
  const destination = action ?? (onNavigate && !historicalOnly && !story.repair_verification ? repair
    ? { label: '查看修复依据', onClick: () => onNavigate(`/changes?repair_reference=${encodeURIComponent(repair.repair_fingerprint)}`) }
    : { label: story.change_context ? '返回本批交付' : '返回当前工作', onClick: () => onNavigate(story.change_context ? `/changes?change_id=${encodeURIComponent(story.change_context.change_id)}` : '/workspace') } : undefined)
  const tone = { PASS: 'pass', BLOCK: 'block', INCONCLUSIVE: 'unknown' }[story.verdict]
  return <header className={`result-overview-header${onNavigate ? ' agent-task-banner' : ''}`}><div className="agent-task-main">
    <div className="result-overview-status"><ResultBadge tone={tone}>{story.verdict === 'PASS' ? '验证通过' : story.verdict === 'BLOCK' ? '发现权限问题' : '证据不足'}</ResultBadge><span>本轮记录已保存</span></div>
    <div className="result-overview-title"><div><h1>{story.repair_verification ? repairLabels[story.repair_verification.status] : runHeading(story)}</h1><p>{summaries[story.verdict]}</p></div>{destination && <Button type="primary" onClick={destination.onClick}>{destination.label}</Button>}</div>
    <div className="result-overview-meta"><span><strong>{story.actions.length}</strong> 项实际检查 <span>·</span> 权限版本 {story.policy_epoch}</span><span>{story.change_context ? '已关联本批交付 · ' : ''}{story.runtime_status === 'MATCHED' ? '已核对检查时运行的代码版本' : story.runtime_status === 'UNCONFIRMED' ? '尚未确认实际运行的代码版本' : '未独立核对实际运行的代码版本'}</span></div>
    {story.runtime_status !== 'MATCHED' && <p className="result-applicability">{story.runtime_status === 'UNCONFIRMED' ? '尚未确认检查前后运行的是同一份代码，不能据此认定当前交付已验收。' : '本轮结论保留其检查范围，尚不能独立证明当前运行加载了哪批代码。'}</p>}
  </div>{onNavigate && <aside className="agent-task-assistance"><ResultAgentHandoff story={story} onNavigate={onNavigate}/></aside>}</header>
}
export function ResultScope({ story }: { story: ResultStory }) {
  const [open, setOpen] = useState(false)
  const visible = useContext(WorkPageVisible)
  useEffect(() => { if (!visible) setOpen(false) }, [visible])
  useEffect(() => setOpen(false), [story.run_id])
  return <><Button type="link" className="result-scope-button" onClick={() => setOpen(true)}>查看本轮范围</Button><Modal title="本轮结果的适用范围" width={1000} open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
    <div className="result-scope-intro"><p>这是检查时保存的范围，后续修改不会改写它。</p><span>{story.actions.length} 项实际检查 · 权限版本 {story.policy_epoch}</span></div>
    <RequirementScopeSummary scopes={story.requirement_scope??[]} historical/>
    <section aria-label="解读结果时的限制"><h3>解读结果时还需注意</h3>{[...new Set([...story.claim_boundary, ...story.actions.flatMap(item => item.claim_boundary)])].map(text => <p key={text}>{text}</p>)}<p className="editorial-muted">每项的计划账号、资源与实际结论，请查看对应检查结果。</p></section>
    <details><summary>核对精确记录引用</summary><p className="result-technical-id">Run：{story.run_id}</p>{story.change_context && <p className="result-technical-id">交付：{story.change_context.change_id}</p>}</details>
  </Modal></>
}
