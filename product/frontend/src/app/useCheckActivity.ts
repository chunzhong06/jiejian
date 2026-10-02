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
  const [dismissedProgress, setDismissedProgress] = useState<{ projectId: string; runId: string } | null>(null)
  const refresh = useRef(onRefresh)
  const settledRun = useRef<string | null>(null)
  const latest = useRef<{ projectId: string; runId: string | null } | null>(null)
  refresh.current = onRefresh
  const runId = active?.run.run_id
  useEffect(() => {
    setCompleted(null); setPaused(false); setDismissedProgress(null); latest.current = null; settledRun.current = null
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
        settledRun.current = latestRunId
        setCompleted({projectId,runId:latestRunId,label:completionLabel(status)})
      }
    }).catch(() => { /* 工作区仍保留原事实，下次明确刷新可重读；不据摘要猜结论。 */ })
    return () => { valid = false }
  }, [projectId, workspaceLoaded, latestRunId])
  useEffect(() => {
    if (!projectId || !runId) return
    let valid = true, failures = 0
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
          settledRun.current = runId
          setCompleted({ projectId, runId, label })
          // 刷新工作区只更新下一任务，用户当前所在页面和未提交输入保持。
          void refresh.current()
          window.dispatchEvent(new Event('jiejian:check-updated'))
          return
        }
        failures = 0; setPaused(false)
        timer = setTimeout(() => { void read() }, 2_000)
      } catch { if (valid) { setPaused(true); failures += 1; timer = setTimeout(() => void read(), Math.min(30000, 2000 * 2 ** Math.min(failures, 3))) } }
    }
    void read()
    return () => { valid = false; if (timer) clearTimeout(timer) }
  }, [projectId, runId])
  // 精确 Run 已读到终态后，陈旧 Workspace 不能让关闭通知退回正在执行。
  // 关闭只隐藏当前 Run 的进度卡片，不停止轮询，也不消费随后到达的完成通知。
  return {
    activeRunId: settledRun.current === runId ? undefined : runId,
    progressDismissed: Boolean(dismissedProgress && dismissedProgress.projectId === projectId && dismissedProgress.runId === runId),
    dismissProgress: () => { if (projectId && runId) setDismissedProgress({ projectId, runId }) },
    paused, completed: completed?.projectId === projectId ? completed : null, dismiss: () => setCompleted(null),
  }
}
