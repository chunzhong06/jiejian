// 结果总览只压缩服务端已发布文案；未知文案原样显示，不根据 HTTP 或效果推算单项结论。
import { Button, Modal } from 'antd'
import { useContext, useEffect, useState, type ReactNode } from 'react'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import type { ActionResultStory, ResultStory } from '../../api/currentChecks'
import { repairLabels } from '../../api/repairs'

const judgements: Record<string, { label: string; tone: string }> = {
  '本次权限要求已得到验证': { label: '符合要求', tone: 'pass' },
  '已确认不应发生的业务后果': { label: '违反要求', tone: 'block' },
  '现有证据不足以完成判断': { label: '待判断', tone: 'unknown' },
}
export function caseJudgement(action: ActionResultStory) {
  return judgements[action.judgement] ?? { label: action.judgement, tone: 'neutral' }
}
export function resourceOwner(action: ActionResultStory) {
  return action.fact_comparison.planned_resource_owner?.label ?? (action.permission.relation === 'OWNS' ? '自己' : action.permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '另一个同权限组账号' : '原资源所有者')
}
export function ResultBadge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`result-badge is-${tone}`}><span aria-hidden="true">{tone === 'pass' ? '✓' : tone === 'block' ? '!' : tone === 'unknown' ? '?' : '·'}</span>{children}</span>
}
const effectLabels: Record<string, string> = {
  '已确认这项业务结果发生': '已发生',
  '在已闭合的观察范围内未发生这项业务结果': '未发生（闭合观察范围内）',
  '无法确认这项业务结果是否发生': '尚不能确认',
}
export function BusinessEffects({ action }: { action: ActionResultStory }) {
  const effects = action.fact_comparison.effects
  return <>{effects.length ? effects.map(effect => <div className="result-effect-fact" key={effect.effect_id}><strong>{effectLabels[effect.judgement] ?? effect.judgement}</strong><span>观察对象：{effect.business_label}</span></div>) : <span className="editorial-muted">尚无完整的业务结果观察。</span>}</>
}
const summaries = {
  PASS: '本轮已执行范围内的权限要求得到验证。后续代码变化需要新的检查。',
  BLOCK: '先核对问题项的实际后果与必要证明，再交给下一批修改。正常业务也要保留。',
  INCONCLUSIVE: '现有事实尚不足以判断。先核对缺少的证明，再准备下一次检查。',
}
export function ResultOverviewHeader({ story, onNavigate, historicalOnly, action }: {
  story: ResultStory; onNavigate?: (path: string) => void; historicalOnly?: boolean
  action?: { label: string; onClick: () => void }
}) {
  const repair = story.verdict === 'BLOCK' ? story.actions.find(item => item.repair_requirement)?.repair_requirement : null
  const destination = action ?? (onNavigate && !historicalOnly ? repair
    ? { label: '查看修复依据', onClick: () => onNavigate(`/changes?repair_reference=${encodeURIComponent(repair.repair_fingerprint)}`) }
    : { label: story.change_context ? '返回本批交付' : '返回当前工作', onClick: () => onNavigate(story.change_context ? `/changes?change_id=${encodeURIComponent(story.change_context.change_id)}` : '/workspace') } : undefined)
  const tone = { PASS: 'pass', BLOCK: 'block', INCONCLUSIVE: 'unknown' }[story.verdict]
  return <header className="result-overview-header">
    <div className="result-overview-status"><ResultBadge tone={tone}>{story.verdict === 'PASS' ? '验证通过' : story.verdict === 'BLOCK' ? '发现权限问题' : '证据不足'}</ResultBadge><span>本轮证据已发布</span></div>
    <div className="result-overview-title"><div><h1>{story.judgement}</h1><p>{summaries[story.verdict]}</p></div>{destination && <Button type="primary" onClick={destination.onClick}>{destination.label} →</Button>}</div>
    <div className="result-overview-meta"><span><strong>{story.actions.length}</strong> 项实际检查 <span>·</span> 权限版本 {story.policy_epoch}</span><span>{story.change_context ? '已关联本批交付 · ' : ''}{story.runtime_status === 'MATCHED' ? '检查前后运行对应已核对' : story.runtime_status === 'UNCONFIRMED' ? '运行对应未确认' : '运行版本未独立核对'}</span></div>
    {story.runtime_status !== 'MATCHED' && <p className="result-applicability">{story.runtime_status === 'UNCONFIRMED' ? '运行身份未能在检查前后保持对应，不能据此认定当前交付已验收。' : '本轮结论保留其检查范围，尚不能独立证明当前运行加载了哪批代码。'}</p>}
    {story.repair_verification && <div className="result-repair-status"><div><strong>{repairLabels[story.repair_verification.status]}</strong><p>本轮已包含原题复验，不需要重复提交同一检查。</p></div>{onNavigate && <Button type="link" onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(story.repair_verification!.source_run_id)}`)}>查看原问题</Button>}</div>}
  </header>
}
export function ResultScope({ story }: { story: ResultStory }) {
  const [open, setOpen] = useState(false)
  const visible = useContext(WorkPageVisible)
  useEffect(() => { if (!visible) setOpen(false) }, [visible])
  useEffect(() => setOpen(false), [story.run_id])
  return <><Button type="text" className="result-scope-button" onClick={() => setOpen(true)}>查看本轮范围 ↗</Button><Modal title="本轮检查范围" open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
    <dl className="result-scope-record"><dt>权限版本</dt><dd>{story.policy_epoch}</dd><dt>检查范围</dt><dd>{story.actions.length} 项实际检查；每项的计划账号、资源与要求见对应结果。</dd><dt>记录属性</dt><dd>已发布快照，不随当前源码和配置改变。</dd></dl>
    {[...new Set([...story.claim_boundary, ...story.actions.flatMap(item => item.claim_boundary)])].map(text => <p key={text}>{text}</p>)}
    <details><summary>核对精确记录引用</summary><p className="result-technical-id">Run：{story.run_id}</p>{story.change_context && <p className="result-technical-id">交付：{story.change_context.change_id}</p>}</details>
  </Modal></>
}
