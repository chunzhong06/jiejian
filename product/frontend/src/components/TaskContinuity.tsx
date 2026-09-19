// 任务位置只读服务端投影；编辑保护仅保留当前页面，不形成第二套完成状态。
import { createContext, useContext, useEffect, useId } from 'react'
import { Button } from 'antd'
import type { WorkspaceViewDto } from '../api/workspace'
import { WorkPageVisible } from '../app/RetainedWorkPages'

export const TaskGuardContext = createContext<(key: string, blocked: boolean) => void>(() => {})

export function useTaskGuard(blocked: boolean) {
  const update = useContext(TaskGuardContext), visible = useContext(WorkPageVisible), key = useId()
  useEffect(() => { update(key, blocked && visible); return () => update(key, false) }, [blocked, visible, key, update])
}

export function TaskJourney({ workspace, pending }: { workspace: WorkspaceViewDto | null; pending?: boolean }) {
  const journey = workspace?.journey
  if (!journey) return null
  return <section className="task-journey" aria-label="当前工作位置">
    <div className="task-journey-heading"><strong>当前工作 · {journey.title}</strong><span>已保存的材料会继续保留</span></div>
    <ol>{journey.steps.map((step, index) => <li key={step.key} data-state={step.status} aria-current={step.status === 'CURRENT' ? 'step' : undefined}>
      <span aria-hidden="true">{step.status === 'COMPLETE' ? '✓' : step.status === 'NEEDS_REVIEW' ? '!' : index + 1}</span>
      {step.label}{step.status === 'NEEDS_REVIEW' && <small>需复核</small>}{step.status === 'UNKNOWN' && <small>待同步</small>}
    </li>)}</ol>
    {pending && <p role="status">有新的待办。当前编辑保持不变，保存或取消后再继续。</p>}
  </section>
}

export function TaskReceipt({ message, pending, onRetry }: { message: string; pending?: string; onRetry?: () => void }) {
  return <div className="task-receipt" data-pending={Boolean(pending)} role="status">
    <div><strong>{message}</strong>{pending && <p>{pending}</p>}</div>
    {onRetry && <Button onClick={onRetry}>重新读取下一步</Button>}
  </div>
}
