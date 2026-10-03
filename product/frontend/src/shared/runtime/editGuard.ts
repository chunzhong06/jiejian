// 页面编辑保护只上报当前可见页面；不推断业务任务是否完成。
import { createContext, useContext, useEffect, useId } from 'react'
import { WorkPageVisible } from './visibility'

export const TaskGuardContext = createContext<(key: string, blocked: boolean) => void>(() => {})

export function useTaskGuard(blocked: boolean) {
  const update = useContext(TaskGuardContext), visible = useContext(WorkPageVisible), key = useId()
  useEffect(() => { update(key, blocked && visible); return () => update(key, false) }, [blocked, visible, key, update])
}
