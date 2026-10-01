// 预设开发演练复用普通变化、检查与原题事实；复制需求不等于真实 Agent 已接收。
import { Alert, Button, Modal, Select, Spin } from 'antd'
import { useContext, useEffect, useRef, useState } from 'react'
import { experienceApi, type OfficialDevelopmentJourneyDto, type OfficialExperienceDto } from '../../api/experience'
import { repairsApi, repairReference, type ProjectRepair } from '../../api/repairs'
import { ApiError } from '../../api/http'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { useLiveRead } from '../../app/useLiveRead'
import './development.css'

export function OfficialDevelopmentJourney({ value, onChanged, onNavigate, onError }: {
  value: OfficialExperienceDto; onChanged: (value: OfficialExperienceDto) => Promise<void>
  onNavigate: (path: string) => void; onError: (error: ApiError) => void
}) {
  const visible = useContext(WorkPageVisible)
  const [journey, setJourney] = useState<OfficialDevelopmentJourneyDto>()
  const [repairs, setRepairs] = useState<ProjectRepair>()
  const [reference, setReference] = useState<string>()
  const [confirm, setConfirm] = useState<'VULNERABLE' | 'FIXED' | null>(null)
  const [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false)
  const [feedback, setFeedback] = useState(''), [canResumeRegistration, setCanResumeRegistration] = useState(false)
  const flight = useRef(false), epoch = useRef(0)
  const pendingTarget = useRef<'VULNERABLE' | 'FIXED' | null>(null)
  const pendingReference = useRef<ReturnType<typeof repairReference> | undefined>(undefined)
  useEffect(() => { epoch.current += 1; return () => { epoch.current += 1 } }, [value.project_id, visible])
  const read = async () => {
    const request = epoch.current
    const [next, repair] = await Promise.all([experienceApi.development(), repairsApi.project(value.project_id!)])
    if (request !== epoch.current) return
    if (next.project_id !== value.project_id || repair.project_id !== value.project_id) throw new ApiError('STATE_PRECONDITION', '示例任务所属项目已变化。')
    setJourney(next); setRepairs(repair)
  }
  const live = useLiveRead(visible && !busy ? value.project_id! : undefined, read, 5000)
  const tasks = repairs?.tasks.filter(task => !['STALE', 'VERIFIED'].includes(task.status)) ?? []
  const task = tasks.find(item => item.contract.repair_fingerprint === reference) ?? (tasks.length === 1 ? tasks[0] : undefined)
  const baseline = journey?.implementation === 'BASELINE'
  const fixed = journey?.implementation === 'FIXED'
  const custom = journey?.implementation === 'CUSTOM'
  const apply = async (resume = false) => {
    const target = resume ? pendingTarget.current : confirm
    if (!target || flight.current || (resume ? !canResumeRegistration : uncertain) || !resume && target === 'FIXED' && !task) return
    const request = epoch.current
    if (!resume) pendingReference.current = target === 'FIXED' && task ? repairReference(task.contract) : undefined
    pendingTarget.current = target
    flight.current = true; setBusy(true); setConfirm(null)
    try {
      const next = await experienceApi.switchVersion(target, pendingReference.current)
      if (request !== epoch.current) return
      setUncertain(false); setCanResumeRegistration(false)
      setFeedback('预设代码变更已登记，请继续核对与验证。')
      await onChanged(next)
    } catch (error) {
      if (request === epoch.current) { setUncertain(true); onError(error as ApiError) }
    } finally { flight.current = false; setBusy(false) }
  }
  return <section className="sample-development" aria-label="官方示例开发流程">
    <header><div><p className="editorial-eyebrow">{custom ? '普通开发协作 · 协作空间' : '预设开发演练 · 协作空间'}</p><h2>官方示例演练</h2></div><span className="sample-development-label">真实执行与独立验证</span></header>
    {!custom && <ol className="sample-development-steps" aria-label="开发演练流程"><li aria-current={baseline ? 'step' : undefined}>确认起始实现</li><li aria-current={journey && !baseline && !fixed ? 'step' : undefined}>异步优化与检查</li><li aria-current={fixed ? 'step' : undefined}>修复与原题复验</li></ol>}
    {!journey ? <div className="sample-development-loading" role="status"><Spin size="small"/><span>正在读取开发与验证状态…</span>{live.retrying && <span>暂时无法读取，正在重试。</span>}</div> : <div className="sample-development-body"><div>
      <h3>{custom ? '已进入真实代码开发' : baseline ? journey.can_optimize ? '起始检查已通过，可以开始优化' : '先验证同步导出的起始实现' : fixed ? journey.repair_verified ? '本次修复已通过原题复验' : '授权顺序已调整，等待独立复验' : journey.verdict === 'BLOCK' ? '检查发现权限问题，继续修复本次修改' : '后台导出已应用，核对这次修改'}</h3>
      <p>{custom ? '源码已有外部修改，预设变更不会覆盖它。请由 Agent 登记实际变化，沿用普通材料核对和独立检查流程；外部修改不等于已经通过验证。' : baseline ? '当前请求会等待项目包生成后返回。本次开发目标是引入后台队列，让用户提交后继续使用页面。' : fixed ? '保留异步导出，先核对权限再创建后台任务。是否修好以原题及正常业务的独立复验为准。' : '观察页面回应和后台项目包是否一致。403 只说明请求被拒绝，不能代替最终业务结果。'}</p>
      <div className="task-focus-actions">
        {journey.run_id && <Button onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(journey.run_id!)}`)}>查看本次检查</Button>}
        {!baseline && task && <Button onClick={() => onNavigate(`/changes?repair_reference=${encodeURIComponent(task.contract.repair_fingerprint)}`)}>查看修复依据</Button>}
        {baseline && journey.can_optimize ? <Button type="primary" disabled={busy || uncertain || live.retrying} onClick={() => setConfirm('VULNERABLE')}>应用预设异步优化</Button>
          : fixed && journey.repair_verified ? <Button type="primary" onClick={() => onNavigate('/changes?view=handoff')}>返回修改记录</Button>
          : !baseline && !fixed && !custom && task ? <Button type="primary" disabled={busy || uncertain || live.retrying} onClick={() => setConfirm('FIXED')}>应用预设修复</Button>
          : <Button type="primary" onClick={() => { const change = fixed ? value.repair_change_id : !custom ? value.vulnerable_change_id : undefined; onNavigate(change ? `/tests?change_id=${encodeURIComponent(change)}` : '/workspace') }}>继续准备与验证</Button>}
      </div>
      {tasks.length > 1 && <Select aria-label="选择待修复原题" value={reference} onChange={setReference} options={tasks.map((item, i) => ({ value: item.contract.repair_fingerprint, label: `原问题 ${i + 1}` }))}/>}
      {feedback && <p role="status">{feedback}</p>}
      {uncertain && <Alert type="warning" message="操作回执或页面同步尚未确认" description="先核对当前实现和修改记录，不重复应用变更。" action={<Button onClick={async () => { try { const next = await experienceApi.status(); await onChanged(next); await read(); const applied = next.scenario_version === pendingTarget.current; const recorded = pendingTarget.current === 'FIXED' ? next.repair_change_id : next.vulnerable_change_id; setCanResumeRegistration(applied && !recorded); if (applied && recorded) setUncertain(false) } catch (error) { onError(error as ApiError) } }}>核对当前状态</Button>}/>}
      {uncertain && canResumeRegistration && <Button loading={busy} onClick={() => void apply(true)}>恢复本批交付登记</Button>}
      {live.retrying && <p role="status">暂时无法同步演练事实，正在重试。</p>}
    </div><aside><h3>持续保留的业务要求</h3><ul><li>负责人可以导出自己的项目包</li><li>成员不能导出其他人的完整项目包</li><li>成员仍可查看日常协作资料</li></ul><p>{journey.reason}</p>{journey.evidence_limited && <p>当前使用受限观察条件，可在应用与环境中恢复。</p>}</aside></div>}
    <footer><p>预设演练沿用同一套修改记录与检查流程。预设修改明确标注来源，不表示 Codex 已编写代码；真实开发继续在原客户端进行。</p></footer>
    <Modal open={confirm !== null} title={confirm === 'FIXED' ? '应用预设修复？' : '应用预设异步优化？'} okText="应用代码变更" cancelText="取消" onCancel={() => setConfirm(null)} onOk={() => void apply()} confirmLoading={busy}>
      <p>{confirm === 'FIXED' ? '将授权检查移到派发之前，保留后台导出。' : '将同步导出改为后台队列执行，界鉴会记录这次真实源码变化。'}</p><p>权限要求与历史结果保留；变更不会自动执行检查或产生安全结论。</p>
    </Modal>
  </section>
}
