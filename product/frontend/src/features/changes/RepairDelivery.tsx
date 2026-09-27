// 原题修复阅读面：要求、修改回执与服务端复验状态分开，登记不表示已经修复。
import { Button, Input } from 'antd'
import { ArrowLeftOutlined, CheckOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'
import type { ProjectRepair } from '../../api/repairs'
import { repairLabels, repairReference } from '../../api/repairs'
import type { SourceChangeViewDto } from '../../api/sourceChanges'
import { formatTimestamp } from '../../app/presentation'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { RepairComparison } from './RepairComparison'
import './delivery.css'

export type RepairTask = ProjectRepair['tasks'][number]
export function RepairDelivery({ task, change, onNavigate, onBack, onViewChange, loadingChange }: {
  task: RepairTask; change?: SourceChangeViewDto; onNavigate: (path: string) => void; onBack: () => void; onViewChange: () => void; loadingChange?: boolean
}) {
  const rows = task.comparison ?? [], deny = rows.filter(row => row.role === 'DENY'), retained = rows.filter(row => row.role !== 'DENY')
  const verified = task.status === 'VERIFIED'
  const [copyFeedback, setCopyFeedback] = useState('')
  const [showTaskText, setShowTaskText] = useState(false)
  const taskText = [
    '请处理界鉴记录的原题修复任务，先核对证据，再修改源码。',
    `项目：${task.contract.project_id}`,
    `原检查：${task.contract.source_run_id}；原题：${task.contract.source_case_id}`,
    `repair_reference：${JSON.stringify(repairReference(task.contract))}`,
    '先通过 jiejian_repair_show 读取这项原题要求及原始证据；不要仅凭本段摘要判断。',
    ...deny.map(row => `需要消除：${row.subject_label ?? '原操作账号'}对${row.resource_owner_label ?? '原资源所有者'}的资源执行${row.action_label}时，禁止发生${row.effect_labels.join('、')}。`),
    ...retained.map(row => `必须保留：${row.subject_label ?? '原操作账号'}执行${row.action_label}的正常业务结果（${row.effect_labels.join('、')}）。`),
    '不改变已确认的权限规则、账号、资源归属和证据标准；不得通过关闭正常功能或减少检查掩盖问题。',
    '修改完成后，通过 jiejian_change_submit 登记真实修改及上述 repair_reference，说明实际改动、验证情况和未解决问题。',
    '修复成功以界鉴独立的原题复验为准；执行检查前核对当前项目授权。',
  ].join('\n')
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    setCopyFeedback('')
    setShowTaskText(false)
    const heading = root.current?.querySelector('h1')
    if (heading) { heading.tabIndex = -1; heading.focus() }
  }, [task.task_reference])
  return <div ref={root}><EditorialPage label="修复要求与交付">
    <Button className="delivery-back" type="link" icon={<ArrowLeftOutlined/>} onClick={onBack}>返回 Agent 协作</Button>
    <EditorialHeader eyebrow="Agent 协作 / 原题修复" title="修复要求与交付"><p className="editorial-muted">交付任务、查看修改、核对复验，始终对应同一项原问题。</p></EditorialHeader>
    {!verified && task.status !== 'STALE' && <section className="delivery-surface agent-handoff" aria-label="交给 Agent 的修复任务"><h2>交给 Agent 处理</h2><p>复制已核对的修复要求，粘贴到你的 Coding Agent 对话。Agent 通过 MCP 读取证据并登记修改后，界鉴会同步交付进展。</p><div className="agent-handoff-actions"><Button type="primary" onClick={async () => { try { await navigator.clipboard.writeText(taskText); setCopyFeedback('修复任务已复制，请粘贴到 Agent 对话。尚未发送给 Agent。') } catch { setShowTaskText(true); setCopyFeedback('剪贴板暂不可用，请从下方复制任务内容。') } }}>复制修复任务</Button><Button onClick={() => onNavigate('/tools')}>连接与授权</Button><Button type="link" aria-expanded={showTaskText} onClick={() => setShowTaskText(value => !value)}>查看任务内容</Button></div>{copyFeedback && <p role="status">{copyFeedback}</p>}{showTaskText && <Input.TextArea aria-label="修复任务内容" readOnly value={taskText} autoSize={{ minRows: 8, maxRows: 18 }}/>}</section>}
    <section className="repair-context"><p><span className="editorial-muted">原问题</span><strong>{deny[0]?.action_label ?? '原题记录中的权限问题'}</strong></p><Button type="link" onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(task.contract.source_run_id)}&case_id=${encodeURIComponent(task.contract.source_case_id)}`)}>查看原始证据</Button></section>
    <div className="repair-delivery-grid">
      <section className="delivery-surface repair-requirements" aria-label="本次修复要求"><h2>本次修复要求</h2>
        <section><h3>需要消除的后果</h3>{deny.length ? deny.map(row => <p className="repair-requirement-sentence" key={row.source_case_id}>{row.subject_label ?? '原操作账号'} 操作 {row.resource_owner_label ?? '原资源所有者'} 的资源时，不应发生{row.effect_labels.join('、') || '原题禁止的业务后果'}。</p>) : <p>原规则禁止的业务后果必须消失；逐项说明暂未取得，请查看完整原题。</p>}</section>
        <section><h3>必须保留的正常业务</h3>{retained.length ? retained.map(row => <p className="repair-requirement-sentence" key={`${row.role}:${row.source_case_id}`}>{row.subject_label ?? '原操作账号'} · {row.action_label}<small>资源属于 {row.resource_owner_label ?? '原资源所有者'}，保留{row.effect_labels.join('、') || '原题要求的业务结果'}。</small></p>) : <p>必须保留原正常对照和全部已通过的业务回归；逐项说明暂未取得。</p>}</section>
        <p className="repair-frozen-rule">原权限规则、操作账号、资源归属与证据标准保持不变。</p>
        <details className="delivery-technical"><summary>查看完整要求与前后对照</summary><RepairComparison rows={rows} sourceRunId={task.contract.source_run_id} onNavigate={onNavigate}/><p className="editorial-muted">已冻结的安全回归：{task.contract.regressions.length} 项。</p></details>
      </section>
      <aside className="delivery-surface repair-progress" aria-label="交付进展"><h2>交付进展</h2><ol>
        <li className="is-complete"><span aria-hidden><CheckOutlined/></span><div><h3>原问题已记录</h3><p>原始结果与证据已经保存</p></div></li>
        <li className={task.change_id ? 'is-complete' : 'is-pending'}><span aria-hidden>{task.change_id ? <CheckOutlined/> : '2'}</span><div><h3>{task.change_id ? '修改已登记' : '等待修改登记'}</h3><p>{change ? `来源 ${change.manifest.submitted_by || '未提供'}` : task.change_id ? '已有关联变化，详情暂未取得' : 'Agent 可通过 MCP 登记本批修改'}</p></div></li>
        <li className={verified ? 'is-complete' : 'is-pending'}><span aria-hidden>{verified ? <CheckOutlined/> : '3'}</span><div><h3>{task.status === 'CHANGE_SUBMITTED' || task.status === 'READY_TO_VERIFY' ? '等待独立复验' : repairLabels[task.status]}</h3><p>{verified ? '原题与要求保留的业务通过验证' : '修复结论以服务端原题复验判断为准'}</p></div></li>
      </ol>
      {task.status === 'READY_TO_VERIFY' && task.change_id ? <><Button type="primary" size="large" block onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(task.change_id!)}`)}>复验原题</Button><Button type="link" block loading={loadingChange} onClick={onViewChange}>查看本批修改</Button></> : task.run_id ? <Button type="primary" size="large" block onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(task.run_id!)}`)}>{task.verification ? '查看关联复验结果' : '查看关联检查记录'}</Button> : task.change_id ? <Button type="primary" size="large" block loading={loadingChange} onClick={onViewChange}>查看本批修改</Button> : <Button size="large" block onClick={() => onNavigate('/tools')}>查看 Agent 连接</Button>}
      {change && <details className="delivery-technical"><summary>查看登记回执</summary><p>{change.manifest.reason}</p><p>{formatTimestamp(change.manifest.created_at_us)}</p><code>{change.manifest.change_id}</code><p>登记只确认这批修改已记录，不确认修复成功。</p></details>}
      </aside>
    </div>
    <p className="delivery-footer">Agent 通过 MCP 登记修改后，无需重复填写。原问题与新的检查结果分别保留。</p>
  </EditorialPage></div>
}
