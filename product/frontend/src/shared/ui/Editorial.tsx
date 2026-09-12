// 编辑式任务骨架只组织服务端内容；不推导优先级、准备状态或安全结论。
import { Button } from 'antd'
import type { ReactNode } from 'react'

export function EditorialPage({ children, label }: { children: ReactNode; label?: string }) {
  return <div className="editorial-page" aria-label={label}>{children}</div>
}
export function EditorialHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <header className="editorial-header"><p className="editorial-eyebrow">{eyebrow}</p><h1>{title}</h1>{children}</header>
}
export function TaskFocus({ title, responsibility, systemWillDo, action }: {
  title: string; responsibility: string; systemWillDo?: string
  action?: { label: string; disabled?: boolean; onClick: () => void }
}) {
  return <section className="task-focus" aria-label="当前判断与主任务">
    <h2>{title}</h2><p>{responsibility}</p>
    {systemWillDo && <p className="editorial-muted">系统接下来会：{systemWillDo}</p>}
    {action && <Button type="primary" disabled={action.disabled} onClick={action.onClick}>{action.label}</Button>}
  </section>
}

export type FlowStep = { key: string; title: string; state: 'complete' | 'current' | 'future'; detail?: ReactNode }
// 当前节点由调用者传入权威状态；完成节点压缩，未来节点不展示操作表单。
export function FlowSpine({ label, steps }: { label: string; steps: FlowStep[] }) {
  return <ol className="flow-spine" aria-label={label}>{steps.map((step) => <li key={step.key} className={`flow-step is-${step.state}`} aria-current={step.state === 'current' ? 'step' : undefined}>
    <div className="flow-step-title"><span aria-hidden="true">{step.state === 'complete' ? '✓' : ''}</span><h3>{step.title}</h3></div>
    {step.state === 'current' && step.detail && <div className="flow-step-detail">{step.detail}</div>}
  </li>)}</ol>
}
export function RuleSentence({ children }: { children: ReactNode }) {
  return <p className="rule-sentence">{children}</p>
}
export function EvidenceSurface({ label, children }: { label: string; children: ReactNode }) {
  return <section className="evidence-surface" aria-label={label}><p className="editorial-eyebrow">{label}</p>{children}</section>
}
export function MarginNote({ basis, children, onAdopt }: { basis: string; children: ReactNode; onAdopt?: () => void }) {
  return <aside className="margin-note" aria-label="尚未生效的建议"><p><strong>建议</strong> · 尚未生效</p>{children}<p className="editorial-muted">依据：{basis}</p>{onAdopt && <Button onClick={onAdopt}>采用到草稿</Button>}</aside>
}
