// 预设开发演练复用普通变化、检查与原题事实；复制需求不等于真实 Agent 已接收。
import { Alert, Button, Input, Modal, Select, Spin } from 'antd'
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
  const [feedback, setFeedback] = useState(''), [showBrief, setShowBrief] = useState(false)
  const flight = useRef(false), epoch = useRef(0)
  const pendingTarget = useRef<'VULNERABLE' | 'FIXED' | null>(null)
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
  const brief = `请优化协作空间的项目导出：改为后台任务，提交后可继续使用页面并查看进度。\n项目：${value.project_id}\n开工前通过界鉴 MCP 读取当前业务权限、源码基线与检查状态。\n必须保留：负责人导出自己的完整项目包；普通成员不得导出他人的完整项目包；普通成员可查看日常协作资料。\n修改完成后通过 jiejian_change_submit 一次登记本批真实变化，说明实际修改与未解决问题。不要自行修改已确认权限或把自己的测试当作界鉴复验结论。`
  const apply = async () => {
    if (!confirm || flight.current || uncertain || confirm === 'FIXED' && !task) return
    const target = confirm, request = epoch.current
    pendingTarget.current = target
    flight.current = true; setBusy(true); setConfirm(null)
    try {
      const next = await experienceApi.switchVersion(target, target === 'FIXED' && task ? repairReference(task.contract) : undefined)
      if (request !== epoch.current) return
      setFeedback('预设代码变更已应用，请核对实际变化与材料，再独立验证。')
      await onChanged(next)
    } catch (error) {
      if (request === epoch.current) { setUncertain(true); onError(error as ApiError) }
    } finally { flight.current = false; setBusy(false) }
  }
  return <section className="sample-development" aria-label="官方示例开发流程">
    <header><div><p className="editorial-eyebrow">{custom ? '普通开发协作 · 协作空间' : '预设开发演练 · 协作空间'}</p><h2>让导出更顺畅，保留原来的权限</h2></div><span className="sample-development-label">真实执行与独立验证</span></header>
    {!custom && <ol className="sample-development-steps" aria-label="开发演练流程"><li aria-current={baseline ? 'step' : undefined}>确认起始实现</li><li aria-current={journey && !baseline && !fixed ? 'step' : undefined}>异步优化与检查</li><li aria-current={fixed ? 'step' : undefined}>修复与原题复验</li></ol>}
    {!journey ? <div className="sample-development-loading" role="status"><Spin size="small"/><span>正在读取开发与验证状态…</span>{live.retrying && <span>暂时无法读取，正在重试。</span>}</div> : <div className="sample-development-body"><div>
      <h3>{custom ? '已进入真实代码开发' : baseline ? journey.can_optimize ? '起始检查已通过，可以开始优化' : '先验证同步导出的起始实现' : fixed ? journey.repair_verified ? '本次修复已通过原题复验' : '授权顺序已调整，等待独立复验' : journey.verdict === 'BLOCK' ? '检查发现权限问题，继续修复本次修改' : '后台导出已应用，核对这次修改'}</h3>
      <p>{custom ? '源码已有外部修改，预设变更不会覆盖它。请由 Agent 登记实际变化，沿用普通材料核对和独立检查流程；外部修改不等于已经通过验证。' : baseline ? '当前请求会等待项目包生成后返回。本次开发目标是引入后台队列，让用户提交后继续使用页面。' : fixed ? '保留异步导出，先核对权限再创建后台任务。是否修好以原题及正常业务的独立复验为准。' : '观察页面回应和后台项目包是否一致。403 只说明请求被拒绝，不能代替最终业务结果。'}</p>
      <div className="task-focus-actions">
        {journey.run_id && <Button onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(journey.run_id!)}`)}>查看本次检查</Button>}
        {!baseline && task && <Button onClick={() => onNavigate(`/changes?repair_reference=${encodeURIComponent(task.contract.repair_fingerprint)}`)}>交给真实 Agent 修复</Button>}
        {baseline && journey.can_optimize ? <Button type="primary" disabled={busy || uncertain || live.retrying} onClick={() => setConfirm('VULNERABLE')}>应用预设异步优化</Button>
          : fixed && journey.repair_verified ? <Button type="primary" onClick={() => onNavigate('/tools')}>继续使用真实 Agent 开发</Button>
          : !baseline && !fixed && !custom && task ? <Button type="primary" disabled={busy || uncertain || live.retrying} onClick={() => setConfirm('FIXED')}>应用预设修复</Button>
          : <Button type="primary" onClick={() => { const change = fixed ? value.repair_change_id : !custom ? value.vulnerable_change_id : undefined; onNavigate(change ? `/tests?change_id=${encodeURIComponent(change)}` : '/workspace') }}>继续准备与验证</Button>}
      </div>
      {tasks.length > 1 && <Select aria-label="选择待修复原题" value={reference} onChange={setReference} options={tasks.map((item, i) => ({ value: item.contract.repair_fingerprint, label: `原问题 ${i + 1}` }))}/>}
      {feedback && <p role="status">{feedback}</p>}
      {uncertain && <Alert type="warning" message="操作回执或页面同步尚未确认" description="先核对当前实现和修改记录，不重复应用变更。" action={<Button onClick={async () => { try { const next = await experienceApi.status(); await onChanged(next); await read(); if (next.scenario_version === pendingTarget.current && (pendingTarget.current === 'FIXED' ? next.repair_change_id : next.vulnerable_change_id)) setUncertain(false) } catch (error) { onError(error as ApiError) } }}>核对当前状态</Button>}/>}
      {live.retrying && <p role="status">暂时无法同步演练事实，正在重试。</p>}
    </div><aside><h3>持续保留的业务要求</h3><ul><li>负责人可以导出自己的项目包</li><li>成员不能导出其他人的完整项目包</li><li>成员仍可查看日常协作资料</li></ul><p>{journey.reason}</p>{journey.evidence_limited && <p>当前使用受限观察条件，可在应用与环境中恢复。</p>}</aside></div>}
    <footer><p>预设变更用于重复体验，不代表 Codex 在本轮生成了这些修改。你也可以直接让已连接的 Agent 完成同一需求，由 MCP 登记真实交付。</p><Button type="link" onClick={() => setShowBrief(!showBrief)} aria-expanded={showBrief}>查看给 Codex 的开发需求</Button>{showBrief && <><Input.TextArea aria-label="开发需求" readOnly value={brief} autoSize={{ minRows: 6, maxRows: 12 }}/><Button onClick={async () => { try { await navigator.clipboard.writeText(brief); setFeedback('开发需求已复制，尚未发送给 Agent。') } catch { setFeedback('请从上方文本中手动复制开发需求。') } }}>复制开发需求</Button></>}</footer>
    <Modal open={confirm !== null} title={confirm === 'FIXED' ? '应用预设修复？' : '应用预设异步优化？'} okText="应用代码变更" cancelText="取消" onCancel={() => setConfirm(null)} onOk={() => void apply()} confirmLoading={busy}>
      <p>{confirm === 'FIXED' ? '将授权检查移到派发之前，保留后台导出。' : '将同步导出改为后台队列执行，界鉴会记录这次真实源码变化。'}</p><p>权限要求与历史结果保留；变更不会自动执行检查或产生安全结论。</p>
    </Modal>
  </section>
}
