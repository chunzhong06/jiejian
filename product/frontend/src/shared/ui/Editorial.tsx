// 编辑式任务骨架只组织服务端内容；不推导优先级、准备状态或安全结论。
import { Button } from 'antd'
import { useId, type ReactNode } from 'react'

export function EditorialPage({ children, label, width }: { children: ReactNode; label?: string; width?: 'form' | 'welcome' | 'summary' }) {
  return <div className={`editorial-page${width ? ` editorial-page--${width}` : ''}`} aria-label={label}>{children}</div>
}
export function EditorialHeader({ eyebrow, title, children, status }: { eyebrow?: string; title: string; children?: ReactNode; status?: ReactNode }) {
  const titleId = useId()
  return <header className="editorial-header" aria-labelledby={titleId}>
    {eyebrow && <p className="editorial-eyebrow">{eyebrow}</p>}
    <div className="editorial-heading-row"><h1 id={titleId}>{title}</h1>{status}</div>{children}
  </header>
}

export type FlowStep = { key: string; title: string; state: 'complete' | 'current' | 'future'; detail?: ReactNode }
// 当前节点由调用者传入权威状态；完成节点压缩，未来节点不展示操作表单。
export function FlowSpine({ label, steps, compact = false }: { label: string; steps: FlowStep[]; compact?: boolean }) {
  return <ol className={`flow-spine${compact ? ' is-compact' : ''}`} aria-label={label}>{steps.map((step) => <li key={step.key} className={`flow-step is-${step.state}`} aria-current={step.state === 'current' ? 'step' : undefined}>
    <div className="flow-step-title"><span aria-hidden="true">{step.state === 'complete' ? '✓' : ''}</span><h3>{step.title}</h3></div>
    {step.state === 'current' && step.detail && <div className="flow-step-detail">{step.detail}</div>}
  </li>)}</ol>
}
export function RuleSentence({ children }: { children: ReactNode }) {
  return <p className="rule-sentence">{children}</p>
}
export function MarginNote({ basis, children, onAdopt }: { basis: string; children: ReactNode; onAdopt?: () => void }) {
  return <aside className="margin-note" aria-label="尚未生效的建议"><p><strong>建议</strong> · 尚未生效</p>{children}<p className="editorial-muted">依据：{basis}</p>{onAdopt && <Button onClick={onAdopt}>采用到草稿</Button>}</aside>
}
