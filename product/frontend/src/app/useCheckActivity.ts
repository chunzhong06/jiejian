// 跨页面跟踪本项目已存在的检查；有界只读轮询与完成通知不导航、不创建检查。
import { useEffect, useRef, useState } from 'react'
import { currentChecksApi, type CheckStatus } from '../api/currentChecks'
import { lifecycleLabel } from './presentation'

const completionLabel = (status: CheckStatus) => {
  const verdict = status.result_integrity === 'VALID' ? status.run.verdict : null
  return status.result_integrity === 'INVALID' ? '检查已结束，结果完整性校验失败' : verdict === 'BLOCK' ? '检查完成，发现权限问题' : verdict === 'PASS' ? '检查完成，权限验证通过' : verdict === 'INCONCLUSIVE' ? '检查完成，证据不足' : lifecycleLabel(status.run.lifecycle)
}

export function useCheckActivity(projectId: string | undefined, active: CheckStatus | null | undefined, onRefresh: () => Promise<unknown>, latestRunId?: string | null, workspaceLoaded = false) {
  const [completed, setCompleted] = useState<{ projectId: string; runId: string; label: string } | null>(null)
  const [paused, setPaused] = useState(false)
  const refresh = useRef(onRefresh)
  const latest = useRef<{ projectId: string; runId: string | null } | null>(null)
  refresh.current = onRefresh
  const runId = active?.run.run_id
  useEffect(() => {
    setCompleted(null); setPaused(false); latest.current = null
  }, [projectId])
  useEffect(() => {
    if (!projectId || !workspaceLoaded) return
    const previous = latest.current
    latest.current = {projectId, runId: latestRunId ?? null}
    if (!previous || previous.projectId !== projectId || !latestRunId || previous.runId === latestRunId) return
    let valid = true
    // 短检查可能在两次工作区读取之间结束；首次恢复旧结果不通知，新结果仍核验精确 Run。
    void currentChecksApi.status(latestRunId).then(status => {
      if (valid && status.run.project_id === projectId && status.run.run_id === latestRunId && !['QUEUED','RUNNING'].includes(status.run.lifecycle)) {
        setCompleted({projectId,runId:latestRunId,label:completionLabel(status)})
      }
    }).catch(() => { /* 工作区仍保留原事实，下次明确刷新可重读；不据摘要猜结论。 */ })
    return () => { valid = false }
  }, [projectId, workspaceLoaded, latestRunId])
  useEffect(() => {
    if (!projectId || !runId) return
    let valid = true, reads = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    setPaused(false)
    const read = async () => {
      if (!valid) return
      try {
        const status = await currentChecksApi.status(runId)
        if (!valid) return
        if (status.run.project_id !== projectId || status.run.run_id !== runId) { setPaused(true); return }
        if (!['QUEUED', 'RUNNING'].includes(status.run.lifecycle)) {
          const label = completionLabel(status)
          setCompleted({ projectId, runId, label })
          // 刷新工作区只更新下一任务，用户当前所在页面和未提交输入保持。
          void refresh.current()
          return
        }
        reads += 1
        if (reads >= 150) { setPaused(true); return }
        timer = setTimeout(() => { void read() }, 2_000)
      } catch { if (valid) setPaused(true) }
    }
    void read()
    return () => { valid = false; if (timer) clearTimeout(timer) }
  }, [projectId, runId])
  return { activeRunId: runId, paused, completed: completed?.projectId === projectId ? completed : null, dismiss: () => setCompleted(null) }
}
