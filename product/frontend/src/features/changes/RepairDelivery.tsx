// 原题修复阅读面：要求、修改回执与服务端复验状态分开，登记不表示已经修复。
import { Button } from 'antd'
import { ArrowLeftOutlined, CheckOutlined } from '@ant-design/icons'
import { useEffect, useRef } from 'react'
import type { ProjectRepair } from '../../api/repairs'
import { repairLabels } from '../../api/repairs'
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
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const heading = root.current?.querySelector('h1')
    if (heading) { heading.tabIndex = -1; heading.focus() }
  }, [task.task_reference])
  return <div ref={root}><EditorialPage label="修复要求与交付">
    <Button className="delivery-back" type="link" icon={<ArrowLeftOutlined/>} onClick={onBack}>返回代码变化</Button>
    <EditorialHeader eyebrow="代码变化 / 原题修复" title="修复要求与交付"><p className="editorial-muted">原问题、修改记录与复验结果，在这里对应起来。</p></EditorialHeader>
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
      {task.run_id ? <Button type="primary" size="large" block onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(task.run_id!)}`)}>{task.verification ? '查看关联复验结果' : '查看关联检查记录'}</Button> : task.change_id ? <Button type="primary" size="large" block loading={loadingChange} onClick={onViewChange}>查看本批修改</Button> : <Button size="large" block onClick={() => onNavigate('/tools')}>查看 Agent 连接</Button>}
      {change && <details className="delivery-technical"><summary>查看登记回执</summary><p>{change.manifest.reason}</p><p>{formatTimestamp(change.manifest.created_at_us)}</p><code>{change.manifest.change_id}</code><p>登记只确认这批修改已记录，不确认修复成功。</p></details>}
      </aside>
    </div>
    <p className="delivery-footer">Agent 通过 MCP 登记修改后，无需重复填写。原问题与新的检查结果分别保留。</p>
  </EditorialPage></div>
}
