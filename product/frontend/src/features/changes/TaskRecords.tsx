// 任务和批次均按持久记录分页；历史选择不会修改当前任务或恢复旧写入上下文。
import { Button, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { developmentApi, type DeliveryPage, type TaskHistoryItem } from '../../api/development'
import { ApiError } from '../../api/http'
import { formatTimestamp } from '../../app/presentation'

export function TaskHistory({ projectId, onSelect, onError }: { projectId: string; onSelect: (item: TaskHistoryItem) => void; onError: (error: ApiError) => void }) {
  const [items, setItems] = useState<TaskHistoryItem[]>([]), [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true), [failed, setFailed] = useState(false)
  const epoch = useRef(0)
  const load = async (before?: string | null) => {
    const id = ++epoch.current; setLoading(true)
    try { const page = await developmentApi.history(projectId, before)
      if (id !== epoch.current) return
      if (page.project_id !== projectId) throw new ApiError('STATE_PRECONDITION', '任务历史所属应用不一致。')
      setItems(old => before ? [...old, ...page.items.filter(item => !old.some(existing => existing.task_id === item.task_id))] : page.items); setCursor(page.next_task_id); setFailed(false)
    } catch (error) { if (id === epoch.current) { setFailed(true); onError(error as ApiError) } } finally { if (id === epoch.current) setLoading(false) }
  }
  useEffect(() => { void load(); return () => { epoch.current += 1 } }, [projectId])
  return <section className="task-history" aria-label="历史开发任务"><h2>历史任务</h2><p className="editorial-muted">结束和取消是任务状态，不表示权限验收通过。</p>{items.map(item => <div key={item.task_id} className="task-history-row"><div><strong>{item.title}</strong><p>{({ ACTIVE: '进行中', CLOSED: '已结束', CANCELLED: '已取消' })[item.status]} · 目标修订 {item.revision} · {formatTimestamp(item.updated_at_us)}</p></div><Button onClick={() => onSelect(item)}>查看任务与交付</Button></div>)}{loading && <Spin aria-label="正在读取任务历史"/>}{!loading && !failed && !items.length && <p>尚无开发任务。</p>}{failed && <Button onClick={() => void load(cursor)}>重新读取任务历史</Button>}{cursor && !failed && <Button loading={loading} onClick={() => void load(cursor)}>更早的任务</Button>}</section>
}

export function TaskDeliveryIndex({ projectId, taskId, version, selectedChange, onSelect, onError }: { projectId: string; taskId: string; version?: number; selectedChange?: string; onSelect: (change: string) => void; onError: (error: ApiError) => void }) {
  const [items, setItems] = useState<DeliveryPage['items']>([]), [cursor, setCursor] = useState<number | null>(null)
  const [loading, setLoading] = useState(true), [failed, setFailed] = useState(false)
  const epoch = useRef(0), selection = useRef(selectedChange), select = useRef(onSelect)
  selection.current = selectedChange; select.current = onSelect
  const load = async (before?: number | null) => {
    const id = ++epoch.current; setLoading(true)
    try { const page = await developmentApi.deliveries(projectId, taskId, before)
      if (id !== epoch.current) return
      if (page.project_id !== projectId || page.task_id !== taskId || page.items.some(item => item.delivery.task_id !== taskId || item.delivery.project_id !== projectId)) throw new ApiError('STATE_PRECONDITION', '交付列表关联不一致。')
      setItems(old => before ? [...old, ...page.items.filter(item => !old.some(existing => existing.delivery.delivery_id === item.delivery.delivery_id))] : page.items); setCursor(page.next_ordinal); setFailed(false)
      if (!before && !selection.current && page.items[0]) select.current(page.items[0].delivery.change_id)
    } catch (error) { if (id === epoch.current) { setFailed(true); onError(error as ApiError) } } finally { if (id === epoch.current) setLoading(false) }
  }
  useEffect(() => { setItems([]); void load(); return () => { epoch.current += 1 } }, [projectId, taskId, version])
  return <nav className="change-record-index" aria-label="任务交付批次"><h2>交付批次</h2>{items.map(item => <button key={item.delivery.delivery_id} aria-current={item.delivery.change_id === selectedChange ? 'true' : undefined} onClick={() => onSelect(item.delivery.change_id)}><small>第 {item.delivery.ordinal} 批 · {formatTimestamp(item.delivery.created_at_us)}</small><strong>{item.reason}</strong><span>{item.submitted_by}</span></button>)}{loading && <Spin aria-label="正在读取交付批次"/>}{!loading && !failed && !items.length && <p>该任务尚未登记交付。</p>}{failed && <Button onClick={() => void load(cursor)}>重新读取批次</Button>}{cursor && !failed && <Button loading={loading} onClick={() => void load(cursor)}>更早的交付</Button>}</nav>
}
